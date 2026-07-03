"""jobs/duration.py: parse_duration のユニットテスト（#409 で cli.distill から移設）。"""

from __future__ import annotations

import pytest

from joryu.jobs.duration import parse_duration


def test_parse_duration_hours() -> None:
    assert parse_duration("2h") == 7200


def test_parse_duration_minutes() -> None:
    assert parse_duration("30m") == 1800


def test_parse_duration_seconds() -> None:
    assert parse_duration("45s") == 45


def test_parse_duration_compound() -> None:
    assert parse_duration("1h30m") == 5400


def test_parse_duration_empty_returns_none() -> None:
    assert parse_duration("") is None
    assert parse_duration(None) is None  # type: ignore[arg-type]


def test_parse_duration_bad() -> None:
    with pytest.raises(ValueError):
        parse_duration("two hours")
