"""Asia/Tokyo 日付コンテキスト (チャット session 用)。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
_WEEKDAY_JA = ("月", "火", "水", "木", "金", "土", "日")


def now_jst(clock: Callable[[], datetime] | None = None) -> datetime:
    if clock is not None:
        return clock()
    return datetime.now(JST)


def format_date_context_ja(now: datetime) -> str:
    local = now.astimezone(JST)
    weekday = _WEEKDAY_JA[local.weekday()]
    return (
        f"今日は {local.year}年{local.month:02d}月{local.day:02d}日 ({weekday}) です。"
        "タイムゾーンは Asia/Tokyo です。"
    )
