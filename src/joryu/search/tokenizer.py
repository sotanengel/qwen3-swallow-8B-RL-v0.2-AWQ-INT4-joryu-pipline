"""CJK bi-gram + ASCII 単語トークナイザ (完全オフライン)。"""

from __future__ import annotations

import re

_ASCII_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+")


def tokenize(text: str) -> list[str]:
    """検索用トークン列を返す。ASCII は単語、CJK は bi-gram。"""
    lowered = text.lower()
    tokens: list[str] = []
    for match in _ASCII_WORD_RE.finditer(lowered):
        tokens.append(match.group())
    for match in _CJK_RE.finditer(lowered):
        run = match.group()
        tokens.extend(run)
        if len(run) >= 2:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens
