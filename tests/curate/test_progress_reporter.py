"""curate/progress_reporter.py のユニットテスト。"""

from __future__ import annotations

from datetime import datetime

from joryu.curate.progress_reporter import CurateProgressReporter


def test_curate_reporter_update_shows_eta() -> None:
    messages: list[str] = []

    def capture(msg: str, **kwargs: object) -> None:
        messages.append(msg)

    reporter = CurateProgressReporter(
        prefix="[joryu-curate]",
        run_total=10,
        log=capture,
        tty=False,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        now_fn=lambda: datetime(2026, 1, 1, 0, 2, 0),
    )
    reporter.update(evaluated_in_run=4, kept=2, rejected=2)
    assert "[joryu-curate] 進捗 4/10 (40%)" in messages[0]
    assert "採用 2 棄却 2" in messages[0]
    assert "残り約 3m" in messages[0]
