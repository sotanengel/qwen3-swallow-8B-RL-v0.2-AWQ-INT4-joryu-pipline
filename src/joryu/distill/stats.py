"""蒸留中 stats 更新 (#251)。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from joryu.dashboard_json import write_dashboard_json
from joryu.distill_live import DistillLiveState
from joryu.stats import compute_stats, resolve_stats_output_path

STATS_REFRESH_INTERVAL_SEC = 3.0


def default_stats_refresher(out_path: Path) -> None:
    """dashboard/public/stats.json を蒸留 JSONL から更新する。"""
    dst = resolve_stats_output_path(out_path=out_path)
    if dst is None:
        return
    stats = compute_stats(out_path)
    live = DistillLiveState.to_dict()
    if live["active"] or live["truncation_retries"]:
        stats["distill_live"] = live
    write_dashboard_json(dst, stats, source_path=out_path)


class StatsRefreshThrottler:
    """蒸留中の stats.json 更新を間引く。"""

    def __init__(
        self,
        out_path: Path,
        refresher: Callable[[Path], None],
        *,
        interval_sec: float = STATS_REFRESH_INTERVAL_SEC,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._out_path = out_path
        self._refresher = refresher
        self._interval = interval_sec
        self._time_fn = time_fn or time.time
        self._last_refresh = -interval_sec

    def maybe_refresh(self, *, force: bool = False) -> None:
        now = self._time_fn()
        if not force and now - self._last_refresh < self._interval:
            return
        self._refresher(self._out_path)
        self._last_refresh = now


__all__ = ["STATS_REFRESH_INTERVAL_SEC", "StatsRefreshThrottler", "default_stats_refresher"]
