"""Tool loop 状態 (#257)。"""

from __future__ import annotations

from dataclasses import dataclass, field

from joryu.tool_calls import ParsedToolCall


@dataclass
class ToolCallState:
    """multi-turn tool loop の 1 ターン分の状態。"""

    parsed: tuple[ParsedToolCall, ...]
    loop_turn: int
    finish_reason: str | None
    recovery_strategy: str | None = None
    recovery_count: int = 0
    suspected_unparsed: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["ToolCallState"]
