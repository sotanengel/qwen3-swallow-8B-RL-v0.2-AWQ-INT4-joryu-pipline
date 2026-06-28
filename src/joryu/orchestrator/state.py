"""FSM 状態遷移 (純関数)。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from joryu.orchestrator.profile import ModelProfile


class OrchestratorStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    SWITCHING = "switching"
    ERROR = "error"


class OrchestratorEvent(StrEnum):
    ENSURE_PROFILE = "ensure_profile"
    HEALTH_OK = "health_ok"
    HEALTH_TIMEOUT = "health_timeout"
    STOP_DONE = "stop_done"
    SHUTDOWN = "shutdown"
    RETRY = "retry"


@dataclass
class OrchestratorState:
    status: OrchestratorStatus = OrchestratorStatus.STOPPED
    active: ModelProfile | None = None
    target: ModelProfile | None = None
    error: str | None = None
    progress: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status.value,
            "active": self.active.value if self.active else None,
            "target": self.target.value if self.target else None,
            "error": self.error,
            "progress": self.progress,
            "ready": self.status == OrchestratorStatus.ACTIVE,
        }


def transition(
    state: OrchestratorState, event: OrchestratorEvent, *, target: ModelProfile | None = None
) -> OrchestratorState:
    """FSM 遷移。未知の組み合わせは state をそのまま返す。"""
    if event == OrchestratorEvent.ENSURE_PROFILE and target is not None:
        if state.status == OrchestratorStatus.ACTIVE and state.active == target:
            return state
        if state.status == OrchestratorStatus.STOPPED:
            return replace(
                state,
                status=OrchestratorStatus.STARTING,
                target=target,
                active=None,
                error=None,
                progress=f"starting {target.value}",
            )
        if state.status == OrchestratorStatus.ACTIVE and state.active != target:
            return replace(
                state,
                status=OrchestratorStatus.SWITCHING,
                target=target,
                error=None,
                progress=f"switching {state.active.value} -> {target.value}",
            )
        if state.status == OrchestratorStatus.ERROR:
            return replace(
                state,
                status=OrchestratorStatus.STARTING,
                target=target,
                active=None,
                error=None,
                progress=f"retry starting {target.value}",
            )
    if event == OrchestratorEvent.HEALTH_OK and state.status == OrchestratorStatus.STARTING:
        return replace(
            state,
            status=OrchestratorStatus.ACTIVE,
            active=state.target,
            target=None,
            error=None,
            progress=None,
        )
    if event == OrchestratorEvent.HEALTH_TIMEOUT and state.status == OrchestratorStatus.STARTING:
        return replace(
            state,
            status=OrchestratorStatus.ERROR,
            active=None,
            error="health timeout",
            progress=None,
        )
    if event == OrchestratorEvent.STOP_DONE and state.status == OrchestratorStatus.SWITCHING:
        return replace(
            state,
            status=OrchestratorStatus.STARTING,
            active=None,
            progress=f"starting {state.target.value}" if state.target else None,
        )
    if event == OrchestratorEvent.SHUTDOWN:
        return OrchestratorState()
    return state
