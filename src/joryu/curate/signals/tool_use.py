"""tool use 品質シグナル (#114 / compass C13)。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from joryu.tool_intent import thinking_plans_tool_use

from . import SignalResult

_ACTION_CLAIM_RE = re.compile(
    r"(?:"
    r"検索した|調べた|確認した|調査した|参照した|"
    r"web(?:で|を|上で)|インターネットで|ネットで|"
    r"I searched|I looked up|I found online|according to (?:my )?search"
    r")",
    re.IGNORECASE,
)


def _record_has_tools(record: dict[str, Any]) -> bool:
    tools = record.get("tools")
    return isinstance(tools, list) and len(tools) > 0


def _record_has_tool_calls(record: dict[str, Any]) -> bool:
    tool_calls = record.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    for call in tool_calls:
        if isinstance(call, dict) and isinstance(call.get("name"), str) and call["name"]:
            if call["name"] != "<malformed>":
                return True
    return False


@dataclass
class ToolPlannedNotCalled:
    """thinking に tool 意図あり & tool_calls 空 → hard_reject。"""

    code: str = "TOOL-PLAN"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if not _record_has_tools(record) or _record_has_tool_calls(record):
            return SignalResult(self.code, self.version, 1.0, None, False)
        trace = record.get("thinking_trace") or record.get("reasoning") or ""
        planned = isinstance(trace, str) and thinking_plans_tool_use(trace)
        return SignalResult(self.code, self.version, 0.0 if planned else 1.0, planned, planned)


@dataclass
class ActionClaimWithoutCall:
    """行動完了を主張するが tool log 無し → hard_reject。"""

    code: str = "TOOL-CLAIM"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if not _record_has_tools(record) or _record_has_tool_calls(record):
            return SignalResult(self.code, self.version, 1.0, None, False)
        answer = record.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return SignalResult(self.code, self.version, 1.0, None, False)
        claimed = _ACTION_CLAIM_RE.search(answer) is not None
        return SignalResult(self.code, self.version, 0.0 if claimed else 1.0, claimed, claimed)


__all__ = ["ActionClaimWithoutCall", "ToolPlannedNotCalled"]
