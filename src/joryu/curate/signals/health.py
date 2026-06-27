"""健全性スクリーニング用ルールシグナル (Epic #305 / R-02, R-04, R-08, R-09)。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import SignalResult

_END_OK = re.compile(r"[。！？.!?」』）)\]]\s*$")
_FENCE = "```"
_ALLOWED_CTRL = frozenset({9, 10, 13})

_TPL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"<\|im_start\|>",
        r"<\|redacted_im_end\|>",
        r"<\|endoftext\|>",
        r"<\|im_end\|>",
        r"\nim_start\|",
        r"\nassistant\n",
        r"\nuser\n",
    )
)


def _full_response_text(record: dict[str, Any]) -> str:
    tt = record.get("thinking_trace") or record.get("reasoning") or ""
    ans = record.get("answer") or ""
    if tt and ans:
        return f"{tt}\n{ans}"
    return tt or ans


def ends_well(text: str) -> bool:
    """末尾が句点・括弧閉じ・コードフェンス閉じで終わるか。"""
    ans = (text or "").strip()
    if not ans:
        return False
    fence_count = ans.count(_FENCE)
    if fence_count % 2 != 0:
        return False
    if ans.rstrip().endswith(_FENCE):
        return True
    return bool(_END_OK.search(ans))


def find_ctrl_char_issue(text: str) -> str | None:
    """不可視 Unicode / 私用領域 / 置換文字を検出。問題なければ None。"""
    for ch in text:
        cp = ord(ch)
        if cp in _ALLOWED_CTRL:
            continue
        if cp < 32 or (0x7F <= cp <= 0x9F):
            return f"ctrl:{cp}"
        if cp == 0xFFFD:
            return "replacement_char"
        if 0xE000 <= cp <= 0xF8FF:
            return "private_use"
        if cp >= 0xF0000:
            return "supplementary_private"
    return None


def find_template_leak(text: str) -> str | None:
    for pat in _TPL_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


def find_syntax_break(text: str) -> str | None:
    """未閉じバッククォート・括弧の不一致を検出。"""
    if text.count(_FENCE) % 2 != 0:
        return "unclosed_fence"

    # 単一バッククォート (``` 以外)
    stripped = text.replace(_FENCE, "")
    backtick_open = False
    for ch in stripped:
        if ch == "`":
            backtick_open = not backtick_open
    if backtick_open:
        return "unclosed_backtick"

    stack: list[str] = []
    pairs = {"(": ")", "{": "}", "[": "]"}
    for ch in text:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack[-1] != ch:
                return f"mismatch:{ch}"
            stack.pop()

    if stack:
        return f"unclosed:{stack[-1]}"

    # LaTeX $...$ 簡易チェック (エスケープ除外)
    dollar_open = False
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            i += 2
            continue
        if text[i] == "$":
            dollar_open = not dollar_open
        i += 1
    if dollar_open:
        return "unclosed_dollar"

    return None


@dataclass
class EndWell:
    """R-02: 末尾健全性 (TRUNC とは独立のテキスト終端チェック)。"""

    code: str = "END-WELL"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = _full_response_text(record)
        ok = ends_well(text)
        return SignalResult(self.code, self.version, 1.0 if ok else 0.0, ok, hard_reject=not ok)


@dataclass
class CtrlChar:
    """R-04: 文字化け・制御文字。"""

    code: str = "CTRL-CHAR"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = _full_response_text(record)
        prompt = record.get("prompt") or ""
        issue = find_ctrl_char_issue(text) or find_ctrl_char_issue(prompt)
        bad = issue is not None
        return SignalResult(self.code, self.version, 0.0 if bad else 1.0, issue, hard_reject=bad)


@dataclass
class TemplateLeak:
    """R-08: テンプレート / 制御トークン漏れ。"""

    code: str = "TPL-LEAK"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = _full_response_text(record)
        leak = find_template_leak(text)
        bad = leak is not None
        return SignalResult(self.code, self.version, 0.0 if bad else 1.0, leak, hard_reject=bad)


@dataclass
class SyntaxBreak:
    """R-09: 数式・コード構文破損。"""

    code: str = "SYNTAX-BREAK"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = _full_response_text(record)
        issue = find_syntax_break(text)
        bad = issue is not None
        return SignalResult(self.code, self.version, 0.0 if bad else 1.0, issue, hard_reject=bad)


__all__ = [
    "CtrlChar",
    "EndWell",
    "SyntaxBreak",
    "TemplateLeak",
    "ends_well",
    "find_ctrl_char_issue",
    "find_syntax_break",
    "find_template_leak",
]
