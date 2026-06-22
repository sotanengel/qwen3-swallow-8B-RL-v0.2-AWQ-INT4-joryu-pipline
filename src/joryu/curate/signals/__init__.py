"""シグナル抽象 + レジストリ (R-19/R-22 互換)。

`version` を持たせて、後続 PR でシグナルが差し替わった際に scores.jsonl 側で
古いキャッシュを判別できるようにする (R-22 への布石)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SignalResult:
    """シグナル評価結果。"""

    code: str
    version: str
    score: float
    raw: Any
    hard_reject: bool = False


class Signal(Protocol):
    """統計 / LLM シグナル共通インターフェース。"""

    code: str
    version: str

    def evaluate(self, record: dict[str, Any]) -> SignalResult: ...


__all__ = ["Signal", "SignalResult"]
