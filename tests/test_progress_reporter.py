"""progress_reporter.py: 蒸留ループのターミナル進捗表示。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from joryu.progress_reporter import (
    DistillProgressReporter,
    estimate_remaining,
    format_duration,
)


def test_format_duration_seconds_only() -> None:
    assert format_duration(timedelta(seconds=45)) == "45s"


def test_format_duration_hours() -> None:
    assert format_duration(timedelta(hours=1, minutes=2, seconds=30)) == "1h2m30s"


def test_estimate_remaining_with_completed() -> None:
    result = estimate_remaining(timedelta(seconds=100), completed=2, remaining=3)
    assert result == "2m30s"


def test_reporter_log_start() -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=12003,
        already_done=27,
        run_total=100,
        action_label="蒸留",
        log=capture,
        tty=False,
    )
    reporter.log_start()
    assert messages[0].startswith("[joryu-distill] 全体 12003件")
    assert "今回 100件を蒸留" in messages[0]


def test_reporter_update_shows_progress_and_eta() -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=10,
        already_done=5,
        run_total=5,
        action_label="蒸留",
        log=capture,
        tty=False,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        now_fn=lambda: datetime(2026, 1, 1, 0, 1, 40),
    )
    reporter.update(2)
    assert "[joryu-distill] 進捗 2/5 (40%)" in messages[0]
    assert "残り約 2m30s" in messages[0]


def test_reporter_shows_recent_completions() -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=10,
        already_done=0,
        run_total=10,
        action_label="蒸留",
        log=capture,
        tty=False,
    )
    reporter.record_success("プロンプトA", "回答A", style_id="polite")
    reporter.record_success("プロンプトB", "回答B", style_id="casual")
    reporter.update(2)
    joined = "\n".join(messages)
    assert "直近の完了" in joined
    assert "プロンプトA" in joined
    assert "回答A" in joined
    assert "[polite]" in joined


def test_reporter_keeps_at_most_five_recent() -> None:
    reporter = DistillProgressReporter(
        prefix="[x]",
        total_in_bank=10,
        already_done=0,
        run_total=10,
        action_label="蒸留",
        log=lambda *a, **k: None,
        tty=False,
    )
    for i in range(7):
        reporter.record_success(f"p{i}", f"a{i}")
    assert len(reporter.recent_completions()) == 5
    assert reporter.recent_completions()[0].prompt == "p2"
    assert reporter.recent_completions()[-1].prompt == "p6"


def test_reporter_log_finish() -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=5,
        already_done=0,
        run_total=5,
        action_label="蒸留",
        log=capture,
        tty=False,
    )
    reporter.log_finish(3, out_path=Path("data/distilled/out.jsonl"))
    assert messages[-1].startswith("[joryu-distill] 完了: 3 件")
