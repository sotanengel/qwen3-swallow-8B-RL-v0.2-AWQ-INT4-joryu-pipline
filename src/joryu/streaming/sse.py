"""SSE 共通 layer (#261)。"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from joryu.chat.sse import HEARTBEAT_SSE, format_sse, with_heartbeat


class ChatEventType(StrEnum):
    TOKEN = "token"
    TURN_START = "turn_start"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    COLUMN_DONE = "column_done"
    ERROR = "error"
    DONE = "done"


class SSEEncoder:
    """dict event → SSE 文字列。"""

    @staticmethod
    def encode(event: dict[str, Any]) -> str:
        return format_sse(dict(event))

    @staticmethod
    def heartbeat() -> str:
        return HEARTBEAT_SSE


class SSEDecoder:
    """SSE data 行 → dict。"""

    @staticmethod
    def decode_data_line(data: str) -> dict[str, Any] | None:
        if not data.strip() or data.strip() == "[DONE]":
            return None
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None


__all__ = [
    "ChatEventType",
    "SSEDecoder",
    "SSEEncoder",
    "format_sse",
    "with_heartbeat",
]
