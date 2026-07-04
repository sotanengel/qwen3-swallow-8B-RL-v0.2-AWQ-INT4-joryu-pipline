"""distill/progress_reporter.py: 蒸留ループのターミナル進捗表示。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from joryu.distill.progress_reporter import (
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


def test_reporter_log_start(tmp_path: Path) -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=12003,
        run_total=100,
        action_label="蒸留",
        log=capture,
        tty=False,
        out_path=out,
        count_done_variants=lambda _p: 27,
    )
    reporter.log_start()
    assert messages[0].startswith("[joryu-distill] 全体 12003件")
    assert "処理済 27件" in messages[0]
    assert "今回 100件を蒸留" in messages[0]


def test_reporter_update_shows_progress_and_eta(tmp_path: Path) -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    done_state = {"n": 5}

    def count_fn(_p: Path) -> int:
        return done_state["n"]

    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=10,
        run_total=5,
        action_label="蒸留",
        log=capture,
        tty=False,
        out_path=out,
        count_done_variants=count_fn,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        now_fn=lambda: datetime(2026, 1, 1, 0, 1, 40),
    )
    done_state["n"] = 7
    reporter.update(attempted_in_run=2)
    assert "[joryu-distill] 進捗 2/5 (40%)" in messages[0]
    assert "全体 処理済 7/10 未処理 3" in messages[0]
    assert "残り約 2m30s" in messages[0]


def test_reporter_shows_attempts_when_differ_from_jsonl(tmp_path: Path) -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    done_state = {"n": 5}

    def count_fn(_p: Path) -> int:
        return done_state["n"]

    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=10,
        run_total=5,
        action_label="蒸留",
        log=capture,
        tty=False,
        out_path=out,
        count_done_variants=count_fn,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        now_fn=lambda: datetime(2026, 1, 1, 0, 1, 0),
    )
    done_state["n"] = 6
    reporter.update(attempted_in_run=3)
    assert "試行 3/5" in messages[0]


def test_reporter_shows_recent_completions(tmp_path: Path) -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=10,
        run_total=10,
        action_label="蒸留",
        log=capture,
        tty=False,
        out_path=out,
        count_done_variants=lambda _p: 2,
    )
    reporter.record_success("プロンプトA", "回答A", style_id="prose")
    reporter.record_success("プロンプトB", "回答B", style_id="dialog")
    reporter.update(attempted_in_run=2)
    joined = "\n".join(messages)
    assert "直近の完了" in joined
    assert "プロンプトA" in joined
    assert "回答A" in joined
    assert "[prose]" in joined


def test_reporter_keeps_at_most_five_recent(tmp_path: Path) -> None:
    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[x]",
        total_in_bank=10,
        run_total=10,
        action_label="蒸留",
        log=lambda *a, **k: None,
        tty=False,
        out_path=out,
        count_done_variants=lambda _p: 0,
    )
    for i in range(7):
        reporter.record_success(f"p{i}", f"a{i}")
    assert len(reporter.recent_completions()) == 5
    assert reporter.recent_completions()[0].prompt == "p2"
    assert reporter.recent_completions()[-1].prompt == "p6"


def test_reporter_log_finish(tmp_path: Path) -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    out = tmp_path / "responses.jsonl"
    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=5,
        run_total=5,
        action_label="蒸留",
        log=capture,
        tty=False,
        out_path=out,
        count_done_variants=lambda _p: 0,
    )
    reporter.log_finish(3, out_path=Path("data/distilled/out.jsonl"))
    assert messages[-1].startswith("[joryu-distill] 完了: 3 件")
