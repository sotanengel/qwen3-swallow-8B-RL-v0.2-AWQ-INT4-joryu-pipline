"""CLI 進捗表示の共通ユーティリティ (経過時間・ETA)。"""

from __future__ import annotations

from datetime import timedelta

__all__ = ["estimate_remaining", "format_duration"]


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
