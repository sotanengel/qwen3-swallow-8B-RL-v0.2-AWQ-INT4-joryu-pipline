"""出力形式メトリクスのヒューリスティック (#55 早期診断 / 実測検証用)。"""

from __future__ import annotations

import re
from typing import Any

_HEADER_LINE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_BULLET_LINE = re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE)
_NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+\S", re.MULTILINE)
_BOLD = re.compile(r"\*\*.+?\*\*|__.+?__")
_TABLE_LINE = re.compile(r"\|.+\|")


def has_markdown_markers(text: str) -> bool:
    """回答に markdown 形式の特徴が含まれるか判定する。"""
    if not (text or "").strip():
        return False
    if _HEADER_LINE.search(text):
        return True
    if _BULLET_LINE.search(text):
        return True
    if _NUMBERED_LINE.search(text):
        return True
    if _BOLD.search(text):
        return True
    if _TABLE_LINE.search(text):
        return True
    return False


def sentence_count(text: str) -> int:
    """文数を `[。！？\\n]` 分割で数える。"""
    parts = [s.strip() for s in re.split(r"[。！？\n]", text or "") if s.strip()]
    return len(parts)


def format_metrics(text: str) -> dict[str, Any]:
    """1 回答の形式メトリクスを返す。"""
    return {
        "has_markdown": has_markdown_markers(text),
        "sentence_count": sentence_count(text),
        "char_count": len(text or ""),
    }


def aggregate_by_style(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """JSONL レコードを style_id ごとに集計する。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        sid = rec.get("style_id")
        if not isinstance(sid, str) or not sid:
            continue
        answer = rec.get("answer")
        if not isinstance(answer, str):
            continue
        buckets.setdefault(sid, []).append(format_metrics(answer))

    out: dict[str, dict[str, float]] = {}
    for sid, metrics_list in buckets.items():
        n = len(metrics_list)
        if n == 0:
            continue
        md_count = sum(1 for m in metrics_list if m["has_markdown"])
        out[sid] = {
            "count": float(n),
            "md_marker_rate": md_count / n,
            "mean_sentence_count": sum(m["sentence_count"] for m in metrics_list) / n,
            "mean_char_count": sum(m["char_count"] for m in metrics_list) / n,
        }
    return out


def check_style_format_criteria(
    aggregates: dict[str, dict[str, float]],
) -> list[str]:
    """Y1 受け入れ基準。違反メッセージのリスト (空なら OK)。

    Y3 (tone-styles の format suppression) は #90 で tone-styles 削除のため撤回済み。
    """
    errors: list[str] = []
    dialog = aggregates.get("dialog")
    prose = aggregates.get("prose")

    if dialog and prose:
        if dialog["md_marker_rate"] > prose["md_marker_rate"] + 0.1:
            errors.append(
                "Y1: dialog md_marker_rate "
                f"({dialog['md_marker_rate']:.2f}) > prose + 0.1 "
                f"({prose['md_marker_rate']:.2f})"
            )
        if not (2.0 <= dialog["mean_sentence_count"] <= 5.0):
            errors.append(
                f"Y1: dialog mean_sentence_count ({dialog['mean_sentence_count']:.1f}) "
                "not in [2, 5]"
            )

    return errors
