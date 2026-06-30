"""compose / fake バックエンド。"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from joryu.docker_delegate import stop_docker_container
from joryu.docker_paths import resolve_host_repo_root
from joryu.orchestrator.profile import ALWAYS_COMPOSE_PROFILE, ModelProfile, ProfileSpec

logger = logging.getLogger(__name__)


class Backend(Protocol):
    def start_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

    def stop_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

    def stop_other_gpu_profiles(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
    ) -> None: ...

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool: ...

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
    ) -> None:
        for profile, spec in profiles.items():
            if profile == keep:
                continue
            self.stop_profile(profile, spec=spec)

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool:
        del spec, timeout_s
        return profile in self.healthy or profile in self.running

    def current_running(self) -> set[ModelProfile]:
        return set(self.running)

    def mark_healthy(self, profile: ModelProfile) -> None:
        self.healthy.add(profile)


@dataclass
class ComposeBackend:
    repo_root: str
    docker_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    urlopen_fn: Callable | None = None
    _compose_cwd: str = field(init=False)

    def __post_init__(self) -> None:
        self._compose_cwd = str(resolve_host_repo_root(Path(self.repo_root)))

    def _compose(self, *args: str) -> None:
        cmd = ["docker", "compose", *args]
        proc = self.docker_run(
            cmd,
            cwd=self._compose_cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"compose failed ({' '.join(args)}): {stderr}")

    def _stop_gpu_service(self, service: str, compose_profile: str) -> None:
        try:
            self._compose(
                "--profile",
                ALWAYS_COMPOSE_PROFILE,
                "--profile",
                compose_profile,
                "stop",
                service,
            )
        except RuntimeError:
            logger.warning(
                "compose stop failed for %s (profile=%s); falling back to docker stop",
                service,
                compose_profile,
                exc_info=True,
            )
        stop_docker_container(service, docker_run=self.docker_run)

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
        compose_profile = spec.compose_profile or profile.value
        self._stop_gpu_service(spec.service, compose_profile)

    def stop_other_gpu_profiles(
        self,
        keep: ModelProfile,
        *,
        profiles: dict[ModelProfile, ProfileSpec],
    ) -> None:
        for profile, spec in profiles.items():
            if profile == keep:
                continue
            compose_profile = spec.compose_profile or profile.value
            self._stop_gpu_service(spec.service, compose_profile)

    def is_healthy(
        self, profile: ModelProfile, *, spec: ProfileSpec, timeout_s: float = 1.0
    ) -> bool:
        del profile, timeout_s
        from joryu.readiness import is_profile_healthy

        return is_profile_healthy(spec, urlopen_fn=self.urlopen_fn)


def resolve_backend(repo_root: str) -> Backend:
    if os.environ.get("JORYU_ORCHESTRATOR_BACKEND", "").lower() == "fake":
        return FakeBackend()
    return ComposeBackend(repo_root=repo_root)
