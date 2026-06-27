"""データ品質 R-10 シグナル (#220 / #230, #231, #234)。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import SignalResult

_FACTUAL_NUMBER_RE = re.compile(
    r"(?:"
    r"\d+\s*℃"
    r"|\d+\s*度"
    r"|\d+\s*mm"
    r"|\d+\s*%"
    r"|\d{1,2}:\d{2}"
    r")"
)

_VIRTUAL_DATA_RE = re.compile(
    r"(?:仮想データ|架空|推測値|（例）|\(例\)|サンプルデータ|ダミーデータ)",
    re.IGNORECASE,
)

_PROSE_MARKDOWN_RE = re.compile(
    r"(?:"
    r"```"
    r"|^\s*[-*+]\s"
    r"|^\s*\d+\.\s"
    r"|\|[^\n]+\|"
    r"|^\s*#{1,6}\s"
    r")",
    re.MULTILINE,
)


def _record_has_tools(record: dict[str, Any]) -> bool:
    tools = record.get("tools")
    return isinstance(tools, list) and len(tools) > 0


def _record_has_tool_calls(record: dict[str, Any]) -> bool:
    tool_calls = record.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    return any(
        isinstance(c, dict)
        and isinstance(c.get("name"), str)
        and c["name"] not in ("", "<malformed>")
        for c in tool_calls
    )


@dataclass
class ToolLeak:
    """suspected_unparsed_tool_calls 非空 → hard_reject (失敗 H)。"""

    code: str = "TOOL-LEAK"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        hints = record.get("suspected_unparsed_tool_calls")
        if not isinstance(hints, list) or not hints:
            return SignalResult(self.code, self.version, 1.0, None, False)
        return SignalResult(self.code, self.version, 0.0, len(hints), True)


@dataclass
class FactualHallucination:
    """tools あり & tool_calls 空 & 固有数値 → hard_reject (失敗 B)。"""

    code: str = "FACT-HALL"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if not _record_has_tools(record) or _record_has_tool_calls(record):
            return SignalResult(self.code, self.version, 1.0, None, False)
        answer = record.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return SignalResult(self.code, self.version, 1.0, None, False)
        matched = _FACTUAL_NUMBER_RE.search(answer) is not None
        return SignalResult(self.code, self.version, 0.0 if matched else 1.0, matched, matched)


@dataclass
class VirtualData:
    """仮想データ・架空値フレーズ → hard_reject (失敗 C)。"""

    code: str = "VIRT-DATA"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        answer = record.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return SignalResult(self.code, self.version, 1.0, None, False)
        matched = _VIRTUAL_DATA_RE.search(answer) is not None
        return SignalResult(self.code, self.version, 0.0 if matched else 1.0, matched, matched)


@dataclass
class StyleFormat:
    """style_id 別フォーマット違反 → hard_reject (失敗 I)。"""

    code: str = "STYLE-FMT"
    version: str = "v1"

    _PLAIN_STYLES = frozenset({"prose", "qa_short", "dialog"})

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        style_id = record.get("style_id")
        answer = record.get("answer")
        if not isinstance(style_id, str) or not isinstance(answer, str) or not answer.strip():
            return SignalResult(self.code, self.version, 1.0, None, False)
        if style_id in self._PLAIN_STYLES:
            violation = _PROSE_MARKDOWN_RE.search(answer) is not None
            return SignalResult(
                self.code, self.version, 0.0 if violation else 1.0, style_id, violation
            )
        if style_id == "report":
            return SignalResult(self.code, self.version, 1.0, style_id, False)
        return SignalResult(self.code, self.version, 1.0, None, False)


__all__ = ["FactualHallucination", "StyleFormat", "ToolLeak", "VirtualData"]
