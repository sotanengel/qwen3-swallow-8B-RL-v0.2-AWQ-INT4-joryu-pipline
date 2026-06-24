"""`<tool_call>{...}</tool_call>` ブロックの解析。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


@dataclass(frozen=True)
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    raw: str


def extract_tool_calls(text: str) -> tuple[list[ParsedToolCall], str]:
    """answer から全 `<tool_call>` を抜き、(calls, cleaned_text) を返す。"""
    calls: list[ParsedToolCall] = []

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            calls.append(ParsedToolCall(name="<malformed>", arguments={}, raw=raw))
            return ""
        if not isinstance(payload, dict):
            calls.append(ParsedToolCall(name="<malformed>", arguments={}, raw=raw))
            return ""
        name = payload.get("name")
        arguments = payload.get("arguments")
        if not isinstance(name, str):
            calls.append(ParsedToolCall(name="<malformed>", arguments={}, raw=raw))
            return ""
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(ParsedToolCall(name=name, arguments=arguments, raw=raw))
        return ""

    cleaned = _TOOL_CALL_RE.sub(_replace, text).strip()
    return calls, cleaned
