"""compose / fake バックエンド。"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from joryu.infra.docker.compose_invoke import (
    ComposeProject,
    compose_command_prefix,
    resolve_compose_project,
)
from joryu.infra.docker.delegate import is_docker_container_running, stop_docker_container
from joryu.orchestrator.profile import ALWAYS_COMPOSE_PROFILE, ModelProfile, ProfileSpec

logger = logging.getLogger(__name__)

DEFAULT_COMPOSE_TIMEOUT_S = 120.0
PROFILE_START_COMPOSE_TIMEOUT_S = 3600.0
JUDGE_IMAGE = "joryu-judge:latest"


class Backend(Protocol):
    def start_profile(
        self,
        profile: ModelProfile,
        *,
        spec: ProfileSpec,
        log: Callable[[str], None] | None = None,
    ) -> None: ...

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

    def start_profile(
        self,
        profile: ModelProfile,
        *,
        spec: ProfileSpec,
        log: Callable[[str], None] | None = None,
    ) -> None:
        del spec, log
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
        try:
            proc = self.docker_run(
                cmd,
                cwd=self._project.compose_cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"compose timed out after {timeout}s (args={' '.join(args)})"
            ) from exc
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"compose failed (file={self._project.compose_file}, "
                f"args={' '.join(args)}): {stderr}"
            )

    def _needs_judge_build(self, profile: ModelProfile) -> bool:
        if profile != ModelProfile.SCREENING:
            return False
        from joryu.infra.preflight import docker_image_exists

        return not docker_image_exists(JUDGE_IMAGE, inspect_runner=self.docker_run)

    def start_profile(
        self,
        profile: ModelProfile,
        *,
        spec: ProfileSpec,
        log: Callable[[str], None] | None = None,
    ) -> None:
        compose_profile = spec.compose_profile or profile.value
        args: list[str] = [
            "--profile",
            ALWAYS_COMPOSE_PROFILE,
            "--profile",
            compose_profile,
            "up",
            "-d",
        ]
        if self._needs_judge_build(profile):
            if log is not None:
                log(
                    "[orchestrator] building joryu-judge image "
                    "(first run compiles llama-server with CUDA; may take 10+ minutes)"
                )
            args.append("--build")
        args.append(spec.service)
        if log is not None:
            log(f"[orchestrator] compose up {spec.service} (profile {profile.value})")
        self._compose(*args, timeout_s=PROFILE_START_COMPOSE_TIMEOUT_S)

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

    def _assert_other_gpu_stopped(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
        log: Callable[[str], None] | None = None,
    ) -> None:
        still_running = [
            spec.service
            for profile, spec in profiles.items()
            if profile != keep
            and is_docker_container_running(spec.service, docker_run=self.docker_run)
        ]
        if not still_running:
            return
        msg = f"GPU containers still running after stop: {', '.join(still_running)}"
        if log is not None:
            log(f"[orchestrator] {msg}")
        raise RuntimeError(msg)

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
        self._assert_other_gpu_stopped(keep, profiles=profiles, log=log)

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool:
        del profile, timeout_s
        from joryu.infra.readiness import is_profile_healthy

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
