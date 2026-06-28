"""orchestrator FSM transition テスト。"""

from __future__ import annotations

from joryu.orchestrator.profile import ModelProfile
from joryu.orchestrator.state import (
    OrchestratorEvent,
    OrchestratorState,
    OrchestratorStatus,
    transition,
)


def test_ensure_profile_from_stopped() -> None:
    state = OrchestratorState()
    nxt = transition(state, OrchestratorEvent.ENSURE_PROFILE, target=ModelProfile.DISTILL)
    assert nxt.status == OrchestratorStatus.STARTING
    assert nxt.target == ModelProfile.DISTILL


def test_ensure_profile_idempotent_when_active() -> None:
    state = OrchestratorState(status=OrchestratorStatus.ACTIVE, active=ModelProfile.DISTILL)
    nxt = transition(state, OrchestratorEvent.ENSURE_PROFILE, target=ModelProfile.DISTILL)
    assert nxt is state


def test_ensure_profile_switches_when_active_other() -> None:
    state = OrchestratorState(status=OrchestratorStatus.ACTIVE, active=ModelProfile.DISTILL)
    nxt = transition(state, OrchestratorEvent.ENSURE_PROFILE, target=ModelProfile.SEED_GEN)
    assert nxt.status == OrchestratorStatus.SWITCHING
    assert nxt.target == ModelProfile.SEED_GEN


def test_health_ok_from_starting() -> None:
    state = OrchestratorState(status=OrchestratorStatus.STARTING, target=ModelProfile.SEED_GEN)
    nxt = transition(state, OrchestratorEvent.HEALTH_OK)
    assert nxt.status == OrchestratorStatus.ACTIVE
    assert nxt.active == ModelProfile.SEED_GEN
    assert nxt.target is None


def test_stop_done_then_health_ok() -> None:
    state = OrchestratorState(
        status=OrchestratorStatus.SWITCHING,
        active=ModelProfile.DISTILL,
        target=ModelProfile.SEED_GEN,
    )
    stopped = transition(state, OrchestratorEvent.STOP_DONE)
    assert stopped.status == OrchestratorStatus.STARTING
    ready = transition(stopped, OrchestratorEvent.HEALTH_OK)
    assert ready.active == ModelProfile.SEED_GEN


def test_shutdown_resets() -> None:
    state = OrchestratorState(status=OrchestratorStatus.ACTIVE, active=ModelProfile.DISTILL)
    nxt = transition(state, OrchestratorEvent.SHUTDOWN)
    assert nxt.status == OrchestratorStatus.STOPPED
    assert nxt.active is None
