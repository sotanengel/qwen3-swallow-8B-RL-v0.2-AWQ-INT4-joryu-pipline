"""合成スコア + 採否判定 (R-13) のテスト。"""

from __future__ import annotations

import pytest

from joryu.curate.scoring import (
    CompositeScore,
    build_composite,
    compose_score,
    f_llm,
    f_stat,
    select_by_threshold,
)
from joryu.curate.signals import SignalResult


def _stat(code: str, score: float, hard: bool = False) -> SignalResult:
    return SignalResult(code=code, version="v1", score=score, raw=score, hard_reject=hard)


def test_f_stat_empty_is_zero():
    assert f_stat([]) == 0.0


def test_f_stat_average():
    assert f_stat([_stat("A", 1.0), _stat("B", 0.0)]) == pytest.approx(0.5)


def test_f_llm_none_when_empty():
    assert f_llm([]) is None


def test_compose_score_without_llm_returns_stat():
    assert compose_score(0.7, None, w_stat=0.4, w_llm=0.6) == pytest.approx(0.7)


def test_compose_score_weighted_average():
    out = compose_score(0.5, 1.0, w_stat=0.4, w_llm=0.6)
    assert out == pytest.approx((0.4 * 0.5 + 0.6 * 1.0) / 1.0)


def test_compose_score_zero_weights_returns_zero():
    assert compose_score(0.5, 1.0, w_stat=0.0, w_llm=0.0) == 0.0


def test_build_composite_aggregates_hard_rejects():
    stat = [_stat("LEN-A", 0.0, hard=True), _stat("LANG-JA", 1.0)]
    llm = [_stat("LLM-RUBRIC", 0.8)]
    comp = build_composite(stat_results=stat, llm_results=llm, w_stat=0.4, w_llm=0.6)
    assert comp.hard_rejected
    assert "LEN-A" in comp.hard_rejected_by


def test_select_threshold_basic():
    comps = [
        CompositeScore(stat_score=1, llm_score=None, final_score=0.9),
        CompositeScore(stat_score=1, llm_score=None, final_score=0.4),
        CompositeScore(stat_score=1, llm_score=None, final_score=0.7),
    ]
    out = select_by_threshold(comps, threshold=0.6)
    assert [s.accepted for s in out] == [True, False, True]
    assert out[1].rejected_by == ["BELOW_THRESHOLD"]


def test_select_top_k_prioritizes_high_score():
    comps = [
        CompositeScore(stat_score=1, llm_score=None, final_score=0.1),
        CompositeScore(stat_score=1, llm_score=None, final_score=0.9),
        CompositeScore(stat_score=1, llm_score=None, final_score=0.5),
    ]
    out = select_by_threshold(comps, threshold=0.0, top_k=1)
    assert [s.accepted for s in out] == [False, True, False]


def test_select_keep_rate_rounded():
    comps = [
        CompositeScore(stat_score=1, llm_score=None, final_score=s) for s in [0.1, 0.5, 0.9, 0.3]
    ]
    out = select_by_threshold(comps, threshold=0.0, keep_rate=0.5)
    assert sum(1 for s in out if s.accepted) == 2
    accepted_scores = sorted([s.final_score for s in out if s.accepted], reverse=True)
    assert accepted_scores == [0.9, 0.5]


def test_select_hard_rejected_never_accepted():
    comps = [
        CompositeScore(
            stat_score=1,
            llm_score=None,
            final_score=0.99,
            hard_rejected_by=["LEN-A"],
        ),
        CompositeScore(stat_score=1, llm_score=None, final_score=0.5),
    ]
    out = select_by_threshold(comps, threshold=0.3)
    assert [s.accepted for s in out] == [False, True]
    assert out[0].rejected_by == ["LEN-A"]
