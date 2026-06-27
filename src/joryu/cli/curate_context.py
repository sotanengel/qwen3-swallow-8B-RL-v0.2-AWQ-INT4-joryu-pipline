"""#253: Curate CLI 分割 — Context。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from joryu.config import Config
from joryu.curate.cache import CacheIndex
from joryu.curate.judge_client import JudgeClient
from joryu.curate.signals import Signal


@dataclass
class CurateContext:
    """curate 実行コンテキスト。"""

    config: Config
    args: argparse.Namespace
    src: Path
    dst: Path
    judge: JudgeClient | None
    stat_signals: tuple[Signal, ...]
    cache_index: CacheIndex


__all__ = ["CurateContext"]
