"""`<tool_call>{...}</tool_call>` ブロックの解析。

Qwen3 系モデルは公式仕様では `<tool_call>` タグで tool_call を返すが、
dialog/short answer 系の指示と組み合わせると ```json``` フェンス内に
JSON を吐くケースがある (#92)。保守的条件 (`"name"` AND `"arguments"`
両方を持つ JSON) でフェンス形式もパースする。

#103: タグもフェンスも無い bare top-level JSON `{"name":..., "arguments":...}`
形式も観測されたため、`known_tool_names` 制約付きで抽出する。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_TOOL_CALL_OPEN_RE = re.compile(r"<tool_call>\s*", re.DOTALL)
_TOOL_CALL_CLOSE = "</tool_call>"
_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)
_BARE_NAME_KEY_RE = re.compile(r'"name"\s*:\s*"([^"\\]+)"')
_ORPHAN_TOOL_CALL_RE = re.compile(r"<tool_call\b[^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    raw: str


def _extract_balanced_object(text: str, start: int) -> tuple[str, int] | None:
    """`start` 位置の `{` から対応する `}` までの JSON オブジェクト文字列を返す。"""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    return None


def _looks_like_tool_call_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("name"), str) and "arguments" in payload


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


def _span_overlaps(existing: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(not (end <= s or start >= e) for s, e in existing)


def _collect_tool_call_tag_spans(text: str) -> list[tuple[int, int, ParsedToolCall]]:
    spans: list[tuple[int, int, ParsedToolCall]] = []
    for match in _TOOL_CALL_OPEN_RE.finditer(text):
        brace = text.find("{", match.end())
        if brace < 0:
            continue
        extracted = _extract_balanced_object(text, brace)
        if extracted is None:
            continue
        raw, json_end = extracted
        close = text.find(_TOOL_CALL_CLOSE, json_end)
        if close < 0:
            continue
        span_end = close + len(_TOOL_CALL_CLOSE)
        spans.append((match.start(), span_end, _parse_payload(raw)))
    return spans


def _collect_json_fence_spans(text: str) -> list[tuple[int, int, ParsedToolCall]]:
    spans: list[tuple[int, int, ParsedToolCall]] = []
    occupied: list[tuple[int, int]] = []
    for match in _FENCE_OPEN_RE.finditer(text):
        if _span_overlaps(occupied, match.start(), match.end()):
            continue
        brace = text.find("{", match.end())
        if brace < 0:
            continue
        extracted = _extract_balanced_object(text, brace)
        if extracted is None:
            continue
        raw, json_end = extracted
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not _looks_like_tool_call_payload(payload):
            continue
        close = text.find("```", json_end)
        if close < 0:
            continue
        span_end = close + 3
        if _span_overlaps(occupied, match.start(), span_end):
            continue
        spans.append((match.start(), span_end, _parse_payload(raw)))
        occupied.append((match.start(), span_end))
    return spans


def _collect_bare_json_spans(
    text: str,
    known_tool_names: set[str],
    occupied: list[tuple[int, int]],
) -> list[tuple[int, int, ParsedToolCall]]:
    """`<tool_call>` / ```json``` 外の bare JSON で
    `{"name": <known>, "arguments": {...}}` 形式を抽出する。
    """
    spans: list[tuple[int, int, ParsedToolCall]] = []
    occupied_local = list(occupied)
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        if _span_overlaps(occupied_local, i, i + 1):
            i += 1
            continue
        extracted = _extract_balanced_object(text, i)
        if extracted is None:
            i += 1
            continue
        raw, json_end = extracted
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            i = json_end
            continue
        if not _looks_like_tool_call_payload(payload):
            i = json_end
            continue
        name = payload.get("name")
        if not isinstance(name, str) or name not in known_tool_names:
            i = json_end
            continue
        spans.append((i, json_end, _parse_payload(raw)))
        occupied_local.append((i, json_end))
        i = json_end
    return spans


def extract_tool_calls(
    text: str,
    known_tool_names: set[str] | None = None,
) -> tuple[list[ParsedToolCall], str]:
    """answer から `<tool_call>` と ```json``` フェンス、
    `known_tool_names` が指定されていれば bare JSON 形式も抜き、
    (calls, cleaned_text) を返す。

    `known_tool_names=None` の場合、bare JSON 検出は行わない (旧互換)。
    """
    tag_spans = _collect_tool_call_tag_spans(text)
    occupied = [(s, e) for s, e, _ in tag_spans]
    fence_spans = [
        (s, e, call)
        for s, e, call in _collect_json_fence_spans(text)
        if not _span_overlaps(occupied, s, e)
    ]
    occupied.extend((s, e) for s, e, _ in fence_spans)

    bare_spans: list[tuple[int, int, ParsedToolCall]] = []
    if known_tool_names:
        bare_spans = _collect_bare_json_spans(text, known_tool_names, occupied)

    all_spans = sorted([*tag_spans, *fence_spans, *bare_spans], key=lambda item: item[0])
    calls = [call for _, _, call in all_spans]

    if not all_spans:
        return calls, text.strip()

    cleaned_parts: list[str] = []
    cursor = 0
    for start, end, _call in all_spans:
        cleaned_parts.append(text[cursor:start])
        cursor = end
    cleaned_parts.append(text[cursor:])
    cleaned = "".join(cleaned_parts)
    return calls, cleaned.strip()


def _detect_residual_tool_call_hints(text: str) -> list[str]:
    """parser 抽出後の text に残る tool_call らしき残骸を最大数件返す。

    - `<tool_call>` open tag (閉じ忘れ)
    - bare `{"name": "..."}` 断片 (known_tool_names に拾われなかったケース)
    """
    hints: list[str] = []
    seen: set[str] = set()

    for match in _ORPHAN_TOOL_CALL_RE.finditer(text):
        snippet_end = min(len(text), match.end() + 80)
        snippet = text[match.start() : snippet_end].strip()
        if snippet and snippet not in seen:
            hints.append(snippet)
            seen.add(snippet)
            if len(hints) >= 5:
                return hints

    for match in _BARE_NAME_KEY_RE.finditer(text):
        snippet_start = max(0, match.start() - 16)
        snippet_end = min(len(text), match.end() + 80)
        snippet = text[snippet_start:snippet_end].strip()
        if snippet and snippet not in seen:
            hints.append(snippet)
            seen.add(snippet)
            if len(hints) >= 5:
                break
    return hints


def extract_tool_calls_with_diagnostics(
    text: str,
    known_tool_names: set[str] | None = None,
) -> tuple[list[ParsedToolCall], str, dict[str, Any]]:
    """`extract_tool_calls` に加え、抽出後の text に残った tool_call らしき
    残骸を `diagnostics["suspected_unparsed_tool_calls"]` として返す。
    """
    calls, cleaned = extract_tool_calls(text, known_tool_names=known_tool_names)
    hints = _detect_residual_tool_call_hints(cleaned)
    return calls, cleaned, {"suspected_unparsed_tool_calls": hints}
