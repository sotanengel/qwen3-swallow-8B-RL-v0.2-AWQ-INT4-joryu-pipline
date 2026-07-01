"""compose / fake バックエンド。"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from joryu.compose_invoke import ComposeProject, compose_command_prefix, resolve_compose_project
from joryu.docker_delegate import is_docker_container_running, stop_docker_container
from joryu.orchestrator.profile import ALWAYS_COMPOSE_PROFILE, ModelProfile, ProfileSpec

logger = logging.getLogger(__name__)

DEFAULT_COMPOSE_TIMEOUT_S = 120.0


class Backend(Protocol):
    def start_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

    def stop_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

    def stop_other_gpu_profiles(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
        log: Callable[[str], None] | None = None,
    ) -> None: ...

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool: ...

    def is_profile_container_running(self, profile: ModelProfile, *, spec: ProfileSpec) -> bool: ...

    def current_running(self) -> set[ModelProfile]: ...


@dataclass
class FakeBackend:
    """テスト / CI 用 in-memory バックエンド。"""

    running: set[ModelProfile] = field(default_factory=set)
    healthy: set[ModelProfile] = field(default_factory=set)
    calls: list[tuple[str, ModelProfile]] = field(default_factory=list)

    def start_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None:
        del spec
        self.calls.append(("start", profile))
        self.running.add(profile)

    def stop_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None:
        del spec
        self.calls.append(("stop", profile))
        self.running.discard(profile)
        self.healthy.discard(profile)

    def stop_other_gpu_profiles(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
        log: Callable[[str], None] | None = None,
    ) -> None:
        for profile, spec in profiles.items():
            if profile == keep:
                continue
            if log is not None:
                log(f"[orchestrator] stopping container {spec.service}")
            self.stop_profile(profile, spec=spec)
            if log is not None:
                log(f"[orchestrator] stopped container {spec.service}")

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool:
        del spec, timeout_s
        return profile in self.healthy or profile in self.running

    def is_profile_container_running(self, profile: ModelProfile, *, spec: ProfileSpec) -> bool:
        del spec
        return profile in self.running

    def current_running(self) -> set[ModelProfile]:
        return set(self.running)

    def mark_healthy(self, profile: ModelProfile) -> None:
        self.healthy.add(profile)


@dataclass
class ComposeBackend:
    repo_root: str
    docker_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    urlopen_fn: Callable | None = None
    compose_timeout_s: float = DEFAULT_COMPOSE_TIMEOUT_S
    _project: ComposeProject = field(init=False)

    def __post_init__(self) -> None:
        self._project = resolve_compose_project(Path(self.repo_root))

    def _compose(self, *args: str, timeout_s: float | None = None) -> None:
        cmd = [*compose_command_prefix(self._project), *args]
        timeout = self.compose_timeout_s if timeout_s is None else timeout_s
        proc = self.docker_run(
            cmd,
            cwd=str(self._project.host_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"compose failed (file={self._project.compose_file}, "
                f"args={' '.join(args)}): {stderr}"
            )

    def _stop_gpu_service(
        self,
        service: str,
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        if log is not None:
            log(f"[orchestrator] stopping container {service}")
        stopped = stop_docker_container(service, docker_run=self.docker_run)
        if log is not None:
            if stopped:
                log(f"[orchestrator] stopped container {service}")
            else:
                log(f"[orchestrator] failed to stop container {service}")

    def start_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None:
        compose_profile = spec.compose_profile or profile.value
        self._compose(
            "--profile",
            ALWAYS_COMPOSE_PROFILE,
            "--profile",
            compose_profile,
            "up",
            "-d",
            spec.service,
        )

    def stop_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None:
        self._stop_gpu_service(spec.service)

    def stop_other_gpu_profiles(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
        log: Callable[[str], None] | None = None,
    ) -> None:
        for profile, spec in profiles.items():
            if profile == keep:
                continue
            self._stop_gpu_service(spec.service, log=log)

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool:
        del profile, timeout_s
        from joryu.readiness import is_profile_healthy

        return is_profile_healthy(spec, urlopen_fn=self.urlopen_fn)

    def is_profile_container_running(self, profile: ModelProfile, *, spec: ProfileSpec) -> bool:
        del profile
        return is_docker_container_running(spec.service, docker_run=self.docker_run)

    def current_running(self) -> set[ModelProfile]:
        return set()


def resolve_backend(repo_root: str) -> Backend:
    if os.environ.get("JORYU_ORCHESTRATOR_BACKEND", "").lower() == "fake":
        return FakeBackend()
    return ComposeBackend(repo_root=repo_root)
