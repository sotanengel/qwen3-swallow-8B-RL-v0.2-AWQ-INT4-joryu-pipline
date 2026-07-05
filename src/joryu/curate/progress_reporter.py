"""joryu-curate 用ターミナル進捗表示 (ETA 付き)。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from joryu.utils.progress import estimate_remaining, format_duration

__all__ = ["CurateProgressReporter"]

_LOG_INTERVAL_SEC = 3.0


class CurateProgressReporter:
    """評価ループの進捗と残り時間を stderr / ジョブログへ出す。"""

    def __init__(
        self,
        *,
        prefix: str,
        run_total: int,
        log: Callable[..., Any],
        tty: bool | None = None,
        start_time: datetime | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._prefix = prefix
        self._run_total = max(0, run_total)
        self._log = log
        self._tty = sys.stderr.isatty() if tty is None else tty
        self._start_time = start_time or datetime.now()
        self._now_fn = now_fn or datetime.now
        self._last_line_was_progress = False
        self._last_log_at: datetime | None = None

    def log_start(self, *, total_input: int, resume_skipped: int = 0) -> None:
        msg = f"{self._prefix} 入力 {total_input} 件 | 今回評価 {self._run_total} 件"
        if resume_skipped:
            msg += f" (resume スキップ {resume_skipped} 件)"
        self._emit(msg, final=True)

    def update(
        self,
        *,
        evaluated_in_run: int,
        kept: int,
        rejected: int,
    ) -> None:
        if self._run_total == 0:
            return
        now = self._now_fn()
        if not self._tty and self._last_log_at is not None:
            if (now - self._last_log_at).total_seconds() < _LOG_INTERVAL_SEC:
                if evaluated_in_run < self._run_total:
                    return
        self._last_log_at = now

        elapsed = now - self._start_time
        remaining = max(0, self._run_total - evaluated_in_run)
        pct = int(evaluated_in_run * 100 / self._run_total) if self._run_total else 100
        eta = estimate_remaining(elapsed, completed=evaluated_in_run, remaining=remaining)
        eta_text = f"残り約 {eta}" if eta is not None else "残り約 --"
        msg = (
            f"{self._prefix} 進捗 {evaluated_in_run}/{self._run_total} ({pct}%) | "
            f"採用 {kept} 棄却 {rejected} | "
            f"経過 {format_duration(elapsed)} {eta_text}"
        )
        self._emit(msg, final=evaluated_in_run >= self._run_total)

    def _emit(self, msg: str, *, final: bool) -> None:
        if self._tty and not final:
            self._log(msg, file=sys.stderr, end="\r", flush=True)
            self._last_line_was_progress = True
        else:
            if self._last_line_was_progress and self._tty:
                self._log("", file=sys.stderr)
            self._log(msg, file=sys.stderr)
            self._last_line_was_progress = False
