"""Curate Stage Protocol (#258)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from joryu.config import Config
from joryu.curate.cache import CacheIndex
from joryu.curate.signals import SignalResult


@dataclass
class CurateContext:
    """1 レコード curate の共有コンテキスト。"""

    config: Config
    record: dict[str, Any]
    record_hash: str
    cache_index: CacheIndex
    expected_versions: dict[str, str]
    stage_index: int = 0
    signal_results: list[SignalResult] = field(default_factory=list)


class CurateStage(Protocol):
    """curate パイプライン Stage。"""

    name: str

    def apply(self, context: CurateContext) -> CurateContext: ...


__all__ = ["CurateContext", "CurateStage"]
