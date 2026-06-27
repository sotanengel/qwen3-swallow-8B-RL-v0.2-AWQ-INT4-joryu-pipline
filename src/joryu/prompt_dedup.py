"""プロンプト重複抑制 (#235)。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

_PUNCT_MAP = {
    ",": "、",
    ".": "。",
    "，": "、",
    "．": "。",
}


def normalize_prompt(text: str) -> str:
    """比較用プロンプト正規化: NFKC + 空白 trim。"""
    normalized = unicodedata.normalize("NFKC", text.strip())
    return " ".join(normalized.split())


def normalize_prompt_exact(text: str) -> str:
    """Stage1 重複排除用: NFKC + 空白圧縮 + 句読点統一。"""
    normalized = unicodedata.normalize("NFKC", text.strip())
    collapsed = re.sub(r"\s+", " ", normalized)
    for src, dst in _PUNCT_MAP.items():
        collapsed = collapsed.replace(src, dst)
    for ch in ("、", "。"):
        collapsed = collapsed.replace(ch, "")
    return collapsed.strip()


def exact_hash(prompt: str) -> str:
    """正規化後 SHA1 ハッシュ (hex)。"""
    return hashlib.sha1(normalize_prompt_exact(prompt).encode("utf-8")).hexdigest()


class ExactDedup:
    """NFKC + 句読点統一後の完璧一致重複排除 (Stage 1)。"""

    def __init__(self) -> None:
        self._hashes: set[str] = set()

    def seed_from_existing(self, prompts: Iterable[str]) -> None:
        for p in prompts:
            self.add(p)

    def is_duplicate(self, prompt: str) -> bool:
        return exact_hash(prompt) in self._hashes

    def add(self, prompt: str) -> None:
        self._hashes.add(exact_hash(prompt))

    def __len__(self) -> int:
        return len(self._hashes)


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


__all__ = [
    "ExactDedup",
    "exact_hash",
    "normalize_prompt",
    "normalize_prompt_exact",
    "PromptDedupGuard",
]
