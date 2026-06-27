"""Thinking タグ暴走の検知と正規化 (#250)。"""

from __future__ import annotations

_EMPTY_THINK_CLOSE = "</think>"
_MAX_EMPTY_THINK_REPEATS = 5


class ThinkingRunawayError(RuntimeError):
    """空 thinking タグが連続しすぎた。"""


def is_empty_thinking_delta(delta: str) -> bool:
    text = delta.strip()
    return text in (_EMPTY_THINK_CLOSE, "<think></think>")


def strip_empty_thinking_tags(content: str) -> str:
    """assistant content から空 think 閉じタグだけの断片を除去する。"""
    cleaned = content
    while is_empty_thinking_delta(cleaned):
        cleaned = cleaned.replace(_EMPTY_THINK_CLOSE, "").strip()
    return cleaned


def register_empty_thinking_delta(*, delta: str, streak: int) -> int:
    """空 thinking delta を記録し、更新後の連続回数を返す。"""
    if is_empty_thinking_delta(delta):
        return streak + 1
    return 0


def ensure_not_thinking_runaway(streak: int) -> None:
    if streak >= _MAX_EMPTY_THINK_REPEATS:
        raise ThinkingRunawayError("thinking runaway detected")
