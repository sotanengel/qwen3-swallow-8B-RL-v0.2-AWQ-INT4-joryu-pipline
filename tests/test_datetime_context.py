"""datetime_context.py のテスト。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from joryu.datetime_context import JST, format_date_context_ja, now_jst

JST_TZ = ZoneInfo("Asia/Tokyo")


def test_format_date_context_ja_known_date() -> None:
    known = datetime(2026, 6, 27, 8, 0, tzinfo=JST_TZ)
    text = format_date_context_ja(known)
    assert "2026年06月27日" in text
    assert "(土)" in text
    assert "Asia/Tokyo" in text


def test_now_jst_uses_asia_tokyo() -> None:
    fixed = datetime(2026, 1, 1, 12, 0, tzinfo=JST_TZ)

    def _clock() -> datetime:
        return fixed

    result = now_jst(clock=_clock)
    assert result.tzinfo == JST
    assert result == fixed
