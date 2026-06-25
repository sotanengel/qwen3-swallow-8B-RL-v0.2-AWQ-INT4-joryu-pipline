"""thinking trace / answer から tool 使用意図を検出する (#109 / compass C10)。"""

from __future__ import annotations

import re
from typing import Any

from joryu.tool_calls import ParsedToolCall
from joryu.vllm_client import ChatResult

TOOL_INTENT_RE = re.compile(
    r"(?i)(use\s+(?:search|calc|fetch_url|the)\s+function|"
    r"call\s+(?:search|calc|fetch_url)\b|"
    r"(?:we|let's|should|will)\s+(?:use|call)\s+(?:search|calc|fetch_url|a\s+search)|"
    r"search\s+function|fetch_url|tool\s+(?:usage|function)|"
    r"検索ツール|ツールで|ツールを使|関数を呼|web_search|"
    r"<tool_call\b)",
)

_TOOL_NAME_IN_TEXT_RE = re.compile(
    r"(?i)(?:use|call|invoke|using|calling)\s+(?:the\s+)?([a-z_][a-z0-9_]*)"
)


def thinking_plans_tool_use(text: str) -> bool:
    """テキストに tool 使用意図のシグネチャがあるか。"""
    if not isinstance(text, str) or not text.strip():
        return False
    return TOOL_INTENT_RE.search(text) is not None


def infer_planned_tool_name(text: str, known_tool_names: set[str]) -> str | None:
    """thinking / answer から呼び出し予定のツール名を推定する。"""
    if not known_tool_names or not text.strip():
        return None
    for name in sorted(known_tool_names, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9_]){re.escape(name)}(?![a-z0-9_])", text, re.I):
            return name
    match = _TOOL_NAME_IN_TEXT_RE.search(text)
    if match:
        candidate = match.group(1).lower()
        if candidate in known_tool_names:
            return candidate
    return None


def _record_has_tools(tools: list[dict[str, Any]] | None) -> bool:
    return isinstance(tools, list) and len(tools) > 0


def raw_has_unparsed_tool_call(raw_completion: str | None) -> bool:
    """生出力に `<tool_call>` があるが parser が拾えなかったケース (vLLM #39056)。"""
    if not raw_completion:
        return False
    return "<tool_call" in raw_completion.lower()


def needs_tool_call_recovery(
    chat: ChatResult,
    *,
    tools: list[dict[str, Any]] | None,
) -> bool:
    """intent あり + tool_calls 空 (+ tools 提供あり) なら救済対象。"""
    if not _record_has_tools(tools) or chat.tool_calls:
        return False
    combined = "\n".join(
        part for part in (chat.thinking, chat.answer) if isinstance(part, str) and part.strip()
    )
    if thinking_plans_tool_use(combined):
        return True
    if chat.suspected_unparsed_tool_calls:
        return True
    if raw_has_unparsed_tool_call(chat.raw_completion):
        return True
    return False


def chat_has_tool_calls(chat: ChatResult) -> bool:
    """有効な tool_call が 1 件以上あるか (<malformed> は除く)。"""
    return any(
        isinstance(call, ParsedToolCall) and call.name not in ("", "<malformed>")
        for call in chat.tool_calls
    )


__all__ = [
    "TOOL_INTENT_RE",
    "chat_has_tool_calls",
    "infer_planned_tool_name",
    "needs_tool_call_recovery",
    "raw_has_unparsed_tool_call",
    "thinking_plans_tool_use",
]
