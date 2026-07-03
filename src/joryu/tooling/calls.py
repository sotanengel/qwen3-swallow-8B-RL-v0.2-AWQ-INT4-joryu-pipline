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


def _parse_payload(raw: str, payload: dict[str, Any]) -> ParsedToolCall:
    """JSON 既知の tool_call payload を ParsedToolCall に変換する。"""
    raw = raw.strip()
    name = payload["name"]
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    return ParsedToolCall(name=name, arguments=arguments, raw=raw)


def _span_overlaps(existing: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(not (end <= s or start >= e) for s, e in existing)


def _collect_tool_call_tag_spans(
    text: str,
) -> tuple[list[tuple[int, int, ParsedToolCall | None]], list[str]]:
    """`<tool_call>` タグ span を収集する。

    Returns:
        (spans, skipped_hints): spans は (start, end, call|None)。
        call が None の span は cleaned から除去するが calls には含めない。
        skipped_hints は diagnostics 用の生 span 断片。
    """
    spans: list[tuple[int, int, ParsedToolCall | None]] = []
    skipped_hints: list[str] = []
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
        snippet = text[match.start() : span_end].strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            spans.append((match.start(), span_end, None))
            if snippet:
                skipped_hints.append(snippet)
            continue
        if not _looks_like_tool_call_payload(payload):
            spans.append((match.start(), span_end, None))
            if snippet:
                skipped_hints.append(snippet)
            continue
        spans.append((match.start(), span_end, _parse_payload(raw, payload)))
    return spans, skipped_hints


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
        spans.append((match.start(), span_end, _parse_payload(raw, payload)))
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
        spans.append((i, json_end, _parse_payload(raw, payload)))
        occupied_local.append((i, json_end))
        i = json_end
    return spans


def _extract_tool_call_spans(
    text: str,
    known_tool_names: set[str] | None = None,
) -> tuple[list[ParsedToolCall], list[tuple[int, int]], list[str]]:
    """tool_call span を収集し (calls, removal_spans, skipped_hints) を返す。"""
    tag_span_items, tag_skipped_hints = _collect_tool_call_tag_spans(text)
    occupied = [(s, e) for s, e, _ in tag_span_items]
    fence_spans = [
        (s, e, call)
        for s, e, call in _collect_json_fence_spans(text)
        if not _span_overlaps(occupied, s, e)
    ]
    occupied.extend((s, e) for s, e, _ in fence_spans)

    bare_spans: list[tuple[int, int, ParsedToolCall]] = []
    if known_tool_names:
        bare_spans = _collect_bare_json_spans(text, known_tool_names, occupied)

    valid_spans = (
        [(s, e, call) for s, e, call in tag_span_items if call is not None]
        + fence_spans
        + bare_spans
    )
    removal_spans = sorted(
        [(s, e) for s, e, _ in tag_span_items]
        + [(s, e) for s, e, _ in fence_spans]
        + [(s, e) for s, e, _ in bare_spans],
        key=lambda item: item[0],
    )
    calls = [call for _, _, call in valid_spans]
    return calls, removal_spans, tag_skipped_hints


def _clean_text_with_spans(text: str, removal_spans: list[tuple[int, int]]) -> str:
    if not removal_spans:
        return text.strip()
    cleaned_parts: list[str] = []
    cursor = 0
    for start, end in removal_spans:
        cleaned_parts.append(text[cursor:start])
        cursor = end
    cleaned_parts.append(text[cursor:])
    return "".join(cleaned_parts).strip()


def extract_tool_calls(
    text: str,
    known_tool_names: set[str] | None = None,
) -> tuple[list[ParsedToolCall], str]:
    """answer から `<tool_call>` と ```json``` フェンス、
    `known_tool_names` が指定されていれば bare JSON 形式も抜き、
    (calls, cleaned_text) を返す。

    `known_tool_names=None` の場合、bare JSON 検出は行わない (旧互換)。
    """
    calls, removal_spans, _skipped_hints = _extract_tool_call_spans(
        text,
        known_tool_names=known_tool_names,
    )
    return calls, _clean_text_with_spans(text, removal_spans)


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


def is_skipped_empty_tool_call_hint(hint: str) -> bool:
    """Parser が意図的にスキップした空/非 tool_call 形の `<tool_call>` span か。"""
    hint_stripped = hint.strip()
    if not re.match(r"<tool_call\b", hint_stripped, re.IGNORECASE):
        return False
    if not hint_stripped.lower().endswith(_TOOL_CALL_CLOSE.lower()):
        return False
    brace = hint_stripped.find("{")
    if brace < 0:
        return False
    extracted = _extract_balanced_object(hint_stripped, brace)
    if extracted is None:
        return False
    raw, _ = extracted
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return not _looks_like_tool_call_payload(payload)


def raw_has_recoverable_unparsed_tool_call(
    raw_completion: str | None,
    *,
    known_tool_names: set[str] | None = None,
) -> bool:
    """raw 出力に parser が救済すべき未抽出 tool_call があるか。"""
    if not raw_completion or "<tool_call" not in raw_completion.lower():
        return False
    calls, _spans, hints = _extract_tool_call_spans(
        raw_completion,
        known_tool_names=known_tool_names,
    )
    if calls:
        return True
    if hints and all(is_skipped_empty_tool_call_hint(h) for h in hints):
        return False
    return bool(hints)


def extract_tool_calls_with_diagnostics(
    text: str,
    known_tool_names: set[str] | None = None,
) -> tuple[list[ParsedToolCall], str, dict[str, Any]]:
    """`extract_tool_calls` に加え、抽出後の text に残った tool_call らしき
    残骸を `diagnostics["suspected_unparsed_tool_calls"]` として返す。
    """
    calls, removal_spans, skipped_hints = _extract_tool_call_spans(
        text,
        known_tool_names=known_tool_names,
    )
    cleaned = _clean_text_with_spans(text, removal_spans)

    hints = list(skipped_hints)
    seen = set(hints)
    for hint in _detect_residual_tool_call_hints(cleaned):
        if hint not in seen:
            hints.append(hint)
            seen.add(hint)
            if len(hints) >= 5:
                break
    return calls, cleaned, {"suspected_unparsed_tool_calls": hints}
