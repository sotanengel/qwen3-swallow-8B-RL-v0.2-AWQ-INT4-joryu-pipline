"""curate/streaming.py のユニットテスト。"""

from __future__ import annotations

from joryu.curate.scoring import CompositeScore
from joryu.curate.streaming import immediate_selection, uses_streaming_selection


def _composite(*, hard: bool = False, score: float = 0.8) -> CompositeScore:
    return CompositeScore(
        stat_score=score,
        llm_score=score,
        final_score=score,
        hard_rejected_by=["LEN-A"] if hard else [],
        signal_versions={},
        signal_scores={},
        signal_raw={},
    )


def test_uses_streaming_selection_default() -> None:
    assert uses_streaming_selection(
        best_of_n="off",
        top_k=None,
        keep_rate=None,
        cfg_top_k=None,
        cfg_keep_rate=None,
    )


def test_uses_streaming_selection_false_for_best_of_n() -> None:
    assert not uses_streaming_selection(
        best_of_n="auto",
        top_k=None,
        keep_rate=None,
        cfg_top_k=None,
        cfg_keep_rate=None,
    )


def test_immediate_selection_accepts_above_threshold() -> None:
    sel = immediate_selection(_composite(score=0.9), threshold=0.7)
    assert sel.accepted is True
    assert sel.rejected_by == []


def test_immediate_selection_rejects_hard() -> None:
    sel = immediate_selection(_composite(hard=True, score=0.9), threshold=0.0)
    assert sel.accepted is False
    assert "LEN-A" in sel.rejected_by
