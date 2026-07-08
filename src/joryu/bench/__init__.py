"""Bench harness (throughput / quality).

このパッケージは CI で回せる「計測互換層」として設計する。
実 GPU 上の厳密ベンチではなくても、品質シグナル集計と
結果 JSON スキーマの検証ができることを優先する。
"""

from __future__ import annotations

__all__ = [
    "prompts",
    "throughput",
    "quality",
    "compare",
    "report",
]
