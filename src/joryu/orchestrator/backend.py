"""compose / fake バックエンド。"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from joryu.orchestrator.profile import ALWAYS_COMPOSE_PROFILE, ModelProfile, ProfileSpec

logger = logging.getLogger(__name__)


class Backend(Protocol):
    def start_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

    def stop_profile(self, profile: ModelProfile, *, spec: ProfileSpec) -> None: ...

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

    def _compose(self, *args: str) -> None:
        cmd = ["docker", "compose", *args]
        proc = self.docker_run(
            cmd,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"compose failed ({' '.join(args)}): {stderr}")

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
        self._compose("--profile", compose_profile, "stop", spec.service)

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
