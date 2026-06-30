"""ModelOrchestrator 高レベル API。"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from joryu.orchestrator.backend import Backend, FakeBackend, resolve_backend
from joryu.orchestrator.file_lock import file_lock
from joryu.orchestrator.profile import ModelProfile, ProfileSpec
from joryu.orchestrator.state import (
    OrchestratorEvent,
    OrchestratorState,
    OrchestratorStatus,
    transition,
)

logger = logging.getLogger(__name__)

DEFAULT_STATE_REL = "data/system/active_profile.json"
DEFAULT_HEALTH_TIMEOUT_S = 600.0
DEFAULT_POLL_INTERVAL_S = 2.0


@dataclass
class ModelOrchestrator:
    repo_root: Path
    profiles: dict[ModelProfile, ProfileSpec]
    backend: Backend | None = None
    state_path: Path | None = None
    auto_restore: ModelProfile | None = ModelProfile.DISTILL
    health_timeout_s: float = DEFAULT_HEALTH_TIMEOUT_S
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = resolve_backend(str(self.repo_root))
        if self.state_path is None:
            self.state_path = self.repo_root / DEFAULT_STATE_REL
        self._thread_lock = threading.Lock()
        self._subscribers: list[threading.Condition] = []

    def get_state(self) -> OrchestratorState:
        return self._load_state()

    def subscribe(self) -> Iterator[OrchestratorState]:
        """状態変化を yield (SSE 用)。"""
        last: str | None = None
        while True:
            state = self.get_state()
            payload = json.dumps(state.to_dict(), sort_keys=True)
            if payload != last:
                last = payload
                yield state
            time.sleep(self.poll_interval_s)

    def _notify(self) -> None:
        for cond in self._subscribers:
            with cond:
                cond.notify_all()

    def _save_state(self, state: OrchestratorState) -> None:
        assert self.state_path is not None
        payload = {
            **state.to_dict(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        tmp = self.state_path.with_suffix(".tmp")
        with file_lock(self.state_path):
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            tmp.replace(self.state_path)
        self._notify()

    def _load_state(self) -> OrchestratorState:
        assert self.state_path is not None
        if not self.state_path.exists():
            return OrchestratorState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return OrchestratorState()
        active = raw.get("active")
        target = raw.get("target")
        return OrchestratorState(
            status=OrchestratorStatus(raw.get("status", "stopped")),
            active=ModelProfile(active) if active else None,
            target=ModelProfile(target) if target else None,
            error=raw.get("error"),
            progress=raw.get("progress"),
        )

    def profile_ready(self, profile: ModelProfile) -> bool:
        state = self.get_state()
        if state.status == OrchestratorStatus.ACTIVE and state.active == profile:
            return True
        if isinstance(self.backend, FakeBackend):
            return profile in self.backend.healthy or profile in self.backend.running
        spec = self.profiles.get(profile)
        if spec is None:
            return False
        assert self.backend is not None
        return self.backend.is_healthy(profile, spec=spec)

    def _wait_for_profile_health(
        self,
        target: ModelProfile,
        spec: ProfileSpec,
        state: OrchestratorState,
        backend: Backend,
        emit: Callable[[str], None],
    ) -> None:
        deadline = time.monotonic() + self.health_timeout_s
        while time.monotonic() < deadline:
            if backend.is_healthy(target, spec=spec):
                state = transition(state, OrchestratorEvent.HEALTH_OK)
                self._save_state(state)
                emit(f"[orchestrator] profile ready: {target.value}")
                if isinstance(backend, FakeBackend):
                    backend.mark_healthy(target)
                return
            elapsed = int(self.health_timeout_s - (deadline - time.monotonic()))
            state = replace(state, progress=f"waiting health {elapsed}s")
            self._save_state(state)
            time.sleep(self.poll_interval_s)

        state = transition(state, OrchestratorEvent.HEALTH_TIMEOUT)
        self._save_state(state)
        msg = f"profile {target.value} health timeout after {self.health_timeout_s}s"
        raise RuntimeError(msg)

    def ensure_profile(
        self,
        target: ModelProfile,
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        emit = log or logger.info
        with self._thread_lock:
            state = self._load_state()
            if state.status == OrchestratorStatus.ACTIVE and state.active == target:
                emit(f"[orchestrator] profile already active: {target.value}")
                return

            assert self.backend is not None
            backend = self.backend
            spec = self.profiles[target]

            if state.status == OrchestratorStatus.STARTING and state.target == target:
                emit(f"[orchestrator] waiting for profile: {target.value}")
                self._wait_for_profile_health(target, spec, state, backend, emit)
                return

            if state.status == OrchestratorStatus.SWITCHING and state.target == target:
                emit(f"[orchestrator] resuming switch to {target.value}")
                backend.stop_other_gpu_profiles(keep=target, profiles=self.profiles, log=emit)
                state = transition(state, OrchestratorEvent.STOP_DONE)
                self._save_state(state)
                emit(f"[orchestrator] starting {target.value}")
                backend.start_profile(target, spec=spec)
                self._wait_for_profile_health(target, spec, state, backend, emit)
                return

            if state.status == OrchestratorStatus.ERROR:
                emit("[orchestrator] clearing error, stopping other GPU profiles")
                backend.stop_other_gpu_profiles(keep=target, profiles=self.profiles, log=emit)

            if state.status == OrchestratorStatus.STARTING and state.target != target:
                emit(
                    f"[orchestrator] switching from {state.target.value} to {target.value}"
                    if state.target
                    else f"[orchestrator] switching to {target.value}"
                )
                backend.stop_other_gpu_profiles(keep=target, profiles=self.profiles, log=emit)

            state = transition(state, OrchestratorEvent.ENSURE_PROFILE, target=target)
            self._save_state(state)
            emit(f"[orchestrator] ensuring profile: {target.value}")

            if state.status == OrchestratorStatus.SWITCHING:
                emit(f"[orchestrator] stopping other GPU profiles for {target.value}")
                backend.stop_other_gpu_profiles(keep=target, profiles=self.profiles, log=emit)
                state = transition(state, OrchestratorEvent.STOP_DONE)
                self._save_state(state)

            emit(f"[orchestrator] starting {target.value}")
            backend.start_profile(target, spec=spec)
            self._wait_for_profile_health(target, spec, state, backend, emit)

    def maybe_auto_restore(self, *, log: Callable[[str], None] | None = None) -> None:
        if self.auto_restore is None:
            return
        self.ensure_profile(self.auto_restore, log=log)

    def init_distill_active(self) -> None:
        """joryu-up 後に distill を active として記録。"""
        self._save_state(
            OrchestratorState(
                status=OrchestratorStatus.ACTIVE,
                active=ModelProfile.DISTILL,
            )
        )
