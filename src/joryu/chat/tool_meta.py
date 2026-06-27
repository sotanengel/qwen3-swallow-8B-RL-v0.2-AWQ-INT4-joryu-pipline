"""Tool loop 永続化用メタデータ (#296 / Epic #294 Sub#2)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

McpStatus = str  # "up" | "down" | "degraded" | "fallback_local"

_STATUS_PRIORITY = {
    "fallback_local": 4,
    "degraded": 3,
    "up": 2,
    "down": 1,
}


def summarize_tool_result(result: str, *, max_len: int = 200) -> str:
    text = (result or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def read_executor_mcp_status(executor: object | None) -> McpStatus:
    if executor is None:
        return "down"
    status = getattr(executor, "last_mcp_status", None)
    if isinstance(status, str) and status in _STATUS_PRIORITY:
        return status
    return "down"


def merge_mcp_status(current: McpStatus, new: McpStatus) -> McpStatus:
    if _STATUS_PRIORITY.get(new, 0) >= _STATUS_PRIORITY.get(current, 0):
        return new
    return current


@dataclass
class ToolTurnMeta:
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_errors: list[dict[str, Any]] = field(default_factory=list)
    mcp_status: McpStatus = "down"

    def record_success(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        result: str,
        latency_ms: int,
        mcp_status: McpStatus,
    ) -> None:
        self.tool_calls.append(
            {
                "name": name,
                "arguments": arguments,
                "result_summary": summarize_tool_result(result),
                "latency_ms": latency_ms,
                "mcp_status": mcp_status,
            }
        )
        self.mcp_status = merge_mcp_status(self.mcp_status, mcp_status)

    def record_error(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        status: int | None,
        body: str | None,
        retry_count: int,
        mcp_status: McpStatus,
    ) -> None:
        self.tool_errors.append(
            {
                "name": name,
                "arguments": arguments,
                "status": status,
                "body": body,
                "retry_count": retry_count,
            }
        )
        self.mcp_status = merge_mcp_status(self.mcp_status, mcp_status)


__all__ = [
    "ToolTurnMeta",
    "merge_mcp_status",
    "read_executor_mcp_status",
    "summarize_tool_result",
]
