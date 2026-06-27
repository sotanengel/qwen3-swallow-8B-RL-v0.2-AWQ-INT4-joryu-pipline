"""プロンプト重複抑制 (#235)。"""

from __future__ import annotations

import unicodedata
from collections import defaultdict


def normalize_prompt(text: str) -> str:
    """比較用プロンプト正規化: NFKC + 空白 trim。"""
    normalized = unicodedata.normalize("NFKC", text.strip())
    return " ".join(normalized.split())


class PromptDedupGuard:
    """(normalized_prompt, style_id) ごとの追記上限ガード。"""

    def __init__(self, *, max_per_key: int = 5) -> None:
        self._max = max_per_key
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    def should_skip(self, *, prompt: str, style_id: str | None) -> bool:
        key = (normalize_prompt(prompt), style_id or "")
        return self._counts[key] >= self._max

    def record(self, *, prompt: str, style_id: str | None) -> None:
        key = (normalize_prompt(prompt), style_id or "")
        self._counts[key] += 1

    def count(self, *, prompt: str, style_id: str | None) -> int:
        key = (normalize_prompt(prompt), style_id or "")
        return self._counts[key]


__all__ = ["PromptDedupGuard", "normalize_prompt"]
