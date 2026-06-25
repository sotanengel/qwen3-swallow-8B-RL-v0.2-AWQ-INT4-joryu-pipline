"""`<tool_call>{...}</tool_call>` ブロックの解析。

Qwen3 系モデルは公式仕様では `<tool_call>` タグで tool_call を返すが、
dialog/short answer 系の指示と組み合わせると ```json``` フェンス内に
JSON を吐くケースがある (#92)。保守的条件 (`"name"` AND `"arguments"`
両方を持つ JSON) でフェンス形式もパースする。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

# ```json {...} ``` フェンスを検出するための正規表現。
# 誤検出を避けるため "name" と "arguments" 両キーが含まれる JSON のみマッチ。
_TOOL_CALL_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{[^`]*?\"name\"\s*:[^`]*?\"arguments\"\s*:[^`]*?\})\s*```",
    re.DOTALL,
)


@dataclass(frozen=True)
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    raw: str


def _parse_payload(raw: str) -> ParsedToolCall:
    """JSON 文字列を ParsedToolCall に変換。失敗時は `<malformed>` を返す。"""
    raw = raw.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ParsedToolCall(name="<malformed>", arguments={}, raw=raw)
    if not isinstance(payload, dict):
        return ParsedToolCall(name="<malformed>", arguments={}, raw=raw)
    name = payload.get("name")
    arguments = payload.get("arguments")
    if not isinstance(name, str):
        return ParsedToolCall(name="<malformed>", arguments={}, raw=raw)
    if not isinstance(arguments, dict):
        arguments = {}
    return ParsedToolCall(name=name, arguments=arguments, raw=raw)


def extract_tool_calls(text: str) -> tuple[list[ParsedToolCall], str]:
    """answer から `<tool_call>` と ```json``` フェンス両形式を抜き、
    (calls, cleaned_text) を返す。
    """
    calls: list[ParsedToolCall] = []

    def _replace(match: re.Match[str]) -> str:
        calls.append(_parse_payload(match.group(1)))
        return ""

    cleaned = _TOOL_CALL_RE.sub(_replace, text)
    cleaned = _TOOL_CALL_FENCE_RE.sub(_replace, cleaned)
    return calls, cleaned.strip()
