"""joryu.utils.progress のユニットテスト。"""

from __future__ import annotations

from datetime import timedelta

from joryu.utils.progress import estimate_remaining, format_duration


def test_format_duration_seconds_only() -> None:
    assert format_duration(timedelta(seconds=45)) == "45s"


def test_format_duration_hours() -> None:
    assert format_duration(timedelta(hours=1, minutes=2, seconds=30)) == "1h2m30s"


def test_estimate_remaining_with_completed() -> None:
    result = estimate_remaining(timedelta(seconds=100), completed=2, remaining=3)
    assert result == "2m30s"
