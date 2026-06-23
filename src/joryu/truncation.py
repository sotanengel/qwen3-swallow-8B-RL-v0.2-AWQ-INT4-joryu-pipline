"""推論出力の途中打ち切り検出 (finish_reason + ヒューリスティック)。"""

from __future__ import annotations

import re
from typing import Any

_END_OK = re.compile(r"[。！？.!?」』）)\]]\s*$")
_HEADER_LINE = re.compile(r"^#{1,6}\s+\S")


def answer_looks_truncated(answer: str) -> bool:
    """回答テキストが途中で切れているかヒューリスティック判定する。"""
    ans = (answer or "").strip()
    if not ans:
        return True
    if _END_OK.search(ans):
        return False
    last = ans.split("\n")[-1].strip()
    if _HEADER_LINE.match(last):
        return True
    if "|" in last and not last.endswith("|"):
        return True
    if re.search(r"[、，,：:]\s*$", last):
        return True
    if re.search(r"[\u4e00-\u9fff]$", last) and len(ans) > 200:
        return True
    return False


def record_looks_truncated(record: dict[str, Any]) -> bool:
    """JSONL レコードが途中打ち切りか判定する。"""
    fr = record.get("finish_reason")
    if fr == "length":
        return True
    if fr == "stop":
        return False
    return answer_looks_truncated(str(record.get("answer") or ""))
