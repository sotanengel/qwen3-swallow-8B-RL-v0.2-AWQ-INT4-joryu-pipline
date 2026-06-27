"""Tool call 解析 Strategy (#256)。

tag / fence / bare_json を個別 Strategy として切り出し、Composite で統合する。
"""

from __future__ import annotations

from typing import Protocol

from joryu.tool_calls import (
    ParsedToolCall,
    _collect_bare_json_spans,
    _collect_json_fence_spans,
    _collect_tool_call_tag_spans,
    extract_tool_calls,
)


class ToolCallParserStrategy(Protocol):
    """1 形式の tool_call 抽出 Strategy。"""

    def parse(
        self,
        text: str,
        *,
        known_tool_names: set[str] | None = None,
    ) -> tuple[list[ParsedToolCall], list[tuple[int, int]]]: ...


class TagToolCallParser:
    """`<tool_call>{...}</tool_call>` 形式。"""

    def parse(
        self,
        text: str,
        *,
        known_tool_names: set[str] | None = None,
    ) -> tuple[list[ParsedToolCall], list[tuple[int, int]]]:
        del known_tool_names
        tag_items, _ = _collect_tool_call_tag_spans(text)
        calls = [call for _, _, call in tag_items if call is not None]
        spans = [(s, e) for s, e, _ in tag_items]
        return calls, spans


class FenceToolCallParser:
    """```json {...} ``` フェンス形式。"""

    def parse(
        self,
        text: str,
        *,
        known_tool_names: set[str] | None = None,
    ) -> tuple[list[ParsedToolCall], list[tuple[int, int]]]:
        del known_tool_names
        fence_items = _collect_json_fence_spans(text)
        calls = [call for _, _, call in fence_items]
        spans = [(s, e) for s, e, _ in fence_items]
        return calls, spans


class BareJsonToolCallParser:
    """bare top-level JSON `{"name":..., "arguments":...}` 形式。"""

    def parse(
        self,
        text: str,
        *,
        known_tool_names: set[str] | None = None,
    ) -> tuple[list[ParsedToolCall], list[tuple[int, int]]]:
        if not known_tool_names:
            return [], []
        bare_items = _collect_bare_json_spans(text, known_tool_names, occupied=[])
        calls = [call for _, _, call in bare_items]
        spans = [(s, e) for s, e, _ in bare_items]
        return calls, spans


class CompositeToolCallParser:
    """tag → fence → bare_json の順で span を統合する。"""

    def parse(
        self,
        text: str,
        *,
        known_tool_names: set[str] | None = None,
    ) -> tuple[list[ParsedToolCall], str]:
        """(calls, cleaned_text) を返す。`extract_tool_calls` と互換。"""
        return extract_tool_calls(text, known_tool_names=known_tool_names)


__all__ = [
    "BareJsonToolCallParser",
    "CompositeToolCallParser",
    "FenceToolCallParser",
    "TagToolCallParser",
    "ToolCallParserStrategy",
]
