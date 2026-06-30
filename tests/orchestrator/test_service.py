"""ModelOrchestrator + FakeBackend テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.orchestrator.backend import FakeBackend
from joryu.orchestrator.profile import ModelProfile, ProfileSpec
from joryu.orchestrator.service import ModelOrchestrator
from joryu.orchestrator.state import OrchestratorState, OrchestratorStatus


def _profiles() -> dict[ModelProfile, ProfileSpec]:
    return {
        ModelProfile.DISTILL: ProfileSpec(
            name="distill", service="joryu", port=8100, compose_profile="distill"
        ),
        ModelProfile.SEED_GEN: ProfileSpec(
            name="seed_gen", service="joryu-seed", port=8110, compose_profile="seed_gen"
        ),
        ModelProfile.SCREENING: ProfileSpec(
            name="screening",
            service="joryu-judge",
            port=8080,
            kind="llama_server",
            compose_profile="screening",
        ),
    }


@pytest.fixture
def orch(tmp_path: Path) -> ModelOrchestrator:
    backend = FakeBackend()
    return ModelOrchestrator(
        repo_root=tmp_path,
        profiles=_profiles(),
        backend=backend,
        poll_interval_s=0.01,
        health_timeout_s=1.0,
        auto_restore=ModelProfile.DISTILL,
    )


def test_ensure_profile_idempotent(orch: ModelOrchestrator) -> None:
    orch.ensure_profile(ModelProfile.DISTILL)
    state = orch.get_state()
    assert state.status == OrchestratorStatus.ACTIVE
    assert state.active == ModelProfile.DISTILL
    orch.ensure_profile(ModelProfile.DISTILL)
    assert orch.get_state().active == ModelProfile.DISTILL


def test_ensure_profile_switches(orch: ModelOrchestrator) -> None:
    orch.ensure_profile(ModelProfile.DISTILL)
    orch.ensure_profile(ModelProfile.SEED_GEN)
    state = orch.get_state()
    assert state.active == ModelProfile.SEED_GEN
    backend = orch.backend
    assert isinstance(backend, FakeBackend)
    assert ("stop", ModelProfile.DISTILL) in backend.calls
    assert ("start", ModelProfile.SEED_GEN) in backend.calls


def test_maybe_auto_restore(orch: ModelOrchestrator) -> None:
    orch.ensure_profile(ModelProfile.SEED_GEN)
    orch.maybe_auto_restore()
    assert orch.get_state().active == ModelProfile.DISTILL


def test_ensure_profile_waits_when_already_starting(orch: ModelOrchestrator) -> None:
    backend = orch.backend
    assert isinstance(backend, FakeBackend)
    orch._save_state(
        OrchestratorState(
            status=OrchestratorStatus.STARTING,
            target=ModelProfile.SEED_GEN,
            progress="waiting health 10s",
        )
    )
    backend.mark_healthy(ModelProfile.SEED_GEN)
    backend.calls.clear()
    orch.ensure_profile(ModelProfile.SEED_GEN)
    assert ("start", ModelProfile.SEED_GEN) not in backend.calls
    state = orch.get_state()
    assert state.status == OrchestratorStatus.ACTIVE
    assert state.active == ModelProfile.SEED_GEN


def test_ensure_profile_from_error_stops_gpu_first(orch: ModelOrchestrator) -> None:
    backend = orch.backend
    assert isinstance(backend, FakeBackend)
    orch.ensure_profile(ModelProfile.DISTILL)
    orch._save_state(
        OrchestratorState(
            status=OrchestratorStatus.ERROR,
            error="health timeout",
        )
    )
    backend.mark_healthy(ModelProfile.SEED_GEN)
    backend.calls.clear()
    orch.ensure_profile(ModelProfile.SEED_GEN)
    assert ("stop", ModelProfile.DISTILL) in backend.calls
    assert orch.get_state().active == ModelProfile.SEED_GEN


def test_ensure_profile_resumes_switching(orch: ModelOrchestrator) -> None:
    backend = orch.backend
    assert isinstance(backend, FakeBackend)
    orch._save_state(
        OrchestratorState(
            status=OrchestratorStatus.SWITCHING,
            active=ModelProfile.DISTILL,
            target=ModelProfile.SEED_GEN,
            progress="switching distill -> seed_gen",
        )
    )
    backend.mark_healthy(ModelProfile.SEED_GEN)
    logs: list[str] = []
    orch.ensure_profile(ModelProfile.SEED_GEN, log=logs.append)
    assert ("start", ModelProfile.SEED_GEN) in backend.calls
    assert any("resuming switch" in line for line in logs)
    assert orch.get_state().active == ModelProfile.SEED_GEN
