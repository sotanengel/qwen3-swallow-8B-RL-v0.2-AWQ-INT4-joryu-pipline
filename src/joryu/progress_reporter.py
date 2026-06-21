"""蒸留ループのターミナル進捗表示（mjaga eval_progress 移植 + 直近完了表示）。"""

from __future__ import annotations

import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

__all__ = [
    "DistillProgressReporter",
    "RecentCompletion",
    "estimate_remaining",
    "format_duration",
]

_RECENT_MAX = 5
_TRUNC_PROMPT = 60
_TRUNC_ANSWER = 80


@dataclass(frozen=True)
class RecentCompletion:
    """直近完了 1 件の表示用スナップショット。"""

    prompt: str
    answer: str
    style_id: str | None = None


def format_duration(td: timedelta) -> str:
    """timedelta を '1h2m30s' / '45s' 形式の文字列に変換する。"""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return "".join(parts)


def estimate_remaining(
    elapsed: timedelta,
    *,
    completed: int,
    remaining: int,
) -> str | None:
    """完了件数と経過時間から残り時間の推定文字列を返す。"""
    if completed <= 0 or remaining <= 0:
        return None
    avg_seconds = elapsed.total_seconds() / completed
    return format_duration(timedelta(seconds=avg_seconds * remaining))


def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class DistillProgressReporter:
    """joryu-distill 用ターミナル進捗表示。"""

    def __init__(
        self,
        *,
        prefix: str,
        total_in_bank: int,
        already_done: int,
        run_total: int,
        action_label: str,
        log: Callable[..., Any],
        tty: bool | None = None,
        start_time: datetime | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._prefix = prefix
        self._total_in_bank = total_in_bank
        self._already_done = already_done
        self._run_total = run_total
        self._action_label = action_label
        self._log = log
        self._tty = sys.stderr.isatty() if tty is None else tty
        self._start_time = start_time or datetime.now()
        self._now_fn = now_fn or datetime.now
        self._last_line_was_progress = False
        self._recent: deque[RecentCompletion] = deque(maxlen=_RECENT_MAX)

    def recent_completions(self) -> list[RecentCompletion]:
        return list(self._recent)

    def record_success(
        self,
        prompt: str,
        answer: str,
        *,
        style_id: str | None = None,
    ) -> None:
        """成功した 1 件を直近完了リストに追加する。"""
        self._recent.append(RecentCompletion(prompt=prompt, answer=answer, style_id=style_id))

    def log_start(self) -> None:
        """開始時サマリを出力する。"""
        pending = self._total_in_bank - self._already_done
        msg = (
            f"{self._prefix} 全体 {self._total_in_bank}件 | "
            f"処理済 {self._already_done}件 | 未処理 {pending}件 | "
            f"今回 {self._run_total}件を{self._action_label}"
        )
        self._emit(msg, final=True)

    def update(self, completed_in_run: int) -> None:
        """ループ内で1イテレーション完了ごとに進捗を更新する。"""
        processed_total = self._already_done + completed_in_run
        pending_total = self._total_in_bank - processed_total
        elapsed = self._now_fn() - self._start_time
        pct = int(completed_in_run * 100 / self._run_total) if self._run_total else 100
        remaining_in_run = self._run_total - completed_in_run

        eta = estimate_remaining(
            elapsed,
            completed=completed_in_run,
            remaining=remaining_in_run,
        )
        eta_text = f"残り約 {eta}" if eta is not None else "残り約 --"

        msg = (
            f"{self._prefix} 進捗 {completed_in_run}/{self._run_total} ({pct}%) | "
            f"全体 処理済 {processed_total}/{self._total_in_bank} 未処理 {pending_total} | "
            f"経過 {format_duration(elapsed)} {eta_text}"
        )

        if self._recent:
            if self._last_line_was_progress and self._tty:
                self._log("", file=sys.stderr)
                self._last_line_was_progress = False
            self._log(msg, file=sys.stderr)
            self._log(self._format_recent_block(), file=sys.stderr)
            self._last_line_was_progress = False
        else:
            self._emit(msg, final=False)

    def log_finish(self, written: int, *, out_path: Path) -> None:
        """完了サマリを出力する。"""
        if self._last_line_was_progress and self._tty:
            self._log("", file=sys.stderr)
        msg = f"{self._prefix} 完了: {written} 件 → {out_path}"
        self._emit(msg, final=True)

    def _format_recent_block(self) -> str:
        lines = [f"{self._prefix} --- 直近の完了 (最大{_RECENT_MAX}件) ---"]
        for i, item in enumerate(self._recent, 1):
            style = f"[{item.style_id}] " if item.style_id else ""
            prompt = _truncate(item.prompt, _TRUNC_PROMPT)
            answer = _truncate(item.answer, _TRUNC_ANSWER)
            lines.append(f"  {i}. {style}Q: {prompt}")
            lines.append(f"     A: {answer}")
        return "\n".join(lines)

    def _emit(self, msg: str, *, final: bool) -> None:
        if self._tty and not final:
            self._log(msg, file=sys.stderr, end="\r", flush=True)
            self._last_line_was_progress = True
        else:
            self._log(msg, file=sys.stderr)
            self._last_line_was_progress = False
