"""best-of-N 選択テスト (R-12)。"""

from __future__ import annotations

import pytest

from joryu.curate.best_of_n import (
    BEST_OF_N_REJECTED,
    apply_best_of_n,
    parse_strategy,
)
from joryu.curate.judge_client import FakeJudgeClient
from joryu.curate.scoring import CompositeScore


def _comp(stat: float, *, rubric: float | None = None, hard: list | None = None) -> CompositeScore:
    scores: dict[str, float] = {}
    if rubric is not None:
        scores["LLM-RUBRIC"] = rubric
    return CompositeScore(
        stat_score=stat,
        llm_score=None,
        final_score=stat,
        hard_rejected_by=hard or [],
        signal_versions={},
        signal_scores=scores,
        signal_raw={},
    )


# ---------- parse_strategy ----------


def test_parse_strategy_off_variants():
    assert parse_strategy(None) == "off"
    assert parse_strategy("") == "off"
    assert parse_strategy("off") == "off"


def test_parse_strategy_known():
    assert parse_strategy("auto") == "auto"
    assert parse_strategy("rubric_max") == "rubric_max"
    assert parse_strategy("pair_tournament") == "pair_tournament"


def test_parse_strategy_n_form_falls_to_auto():
    assert parse_strategy("n=4") == "auto"


def test_parse_strategy_invalid_raises():
    with pytest.raises(ValueError):
        parse_strategy("garbage")


# ---------- apply_best_of_n ----------


def test_apply_off_does_nothing():
    records = [{"prompt": "p", "mode": "nothinking", "answer": "a"}] * 3
    composites = [_comp(0.5), _comp(0.7), _comp(0.6)]
    res = apply_best_of_n(records, composites, ["h1", "h2", "h3"], strategy="off")
    assert all(r.is_winner for r in res)
    assert all(not c.hard_rejected for c in composites)


def test_apply_rubric_max_picks_top_score():
    records = [{"prompt": "p", "mode": "nothinking", "answer": str(i)} for i in range(3)]
    composites = [_comp(0.5, rubric=0.3), _comp(0.5, rubric=0.9), _comp(0.5, rubric=0.7)]
    res = apply_best_of_n(records, composites, ["h0", "h1", "h2"], strategy="rubric_max")
    assert res[1].is_winner is True
    assert res[0].is_winner is False
    assert res[2].is_winner is False
    assert BEST_OF_N_REJECTED in composites[0].hard_rejected_by
    assert BEST_OF_N_REJECTED in composites[2].hard_rejected_by
    assert composites[1].hard_rejected_by == []


def test_apply_rubric_max_tiebreaker_by_record_hash():
    # 3 件すべて rubric 同点 → record_hash 辞書順最小が勝者
    records = [{"prompt": "p", "mode": "nothinking", "answer": str(i)} for i in range(3)]
    composites = [_comp(0.5, rubric=0.5) for _ in range(3)]
    res = apply_best_of_n(records, composites, ["c", "a", "b"], strategy="rubric_max")
    # 辞書順最小 = "a" (index 1)
    assert res[1].is_winner is True


def test_apply_pair_tournament_uses_judge():
    def scorer(prompt: str, a: str, b: str):
        return "a" if len(a) > len(b) else "b"

    fj = FakeJudgeClient(pair_scorer=scorer)
    records = [
        {"prompt": "p", "mode": "nothinking", "answer": "long answer"},
        {"prompt": "p", "mode": "nothinking", "answer": "short"},
    ]
    composites = [_comp(0.5), _comp(0.5)]
    res = apply_best_of_n(records, composites, ["h0", "h1"], strategy="pair_tournament", judge=fj)
    assert res[0].is_winner is True
    assert res[1].is_winner is False
    assert "LLM-PAIR" in composites[0].signal_scores


def test_apply_skips_hard_rejected_records():
    # 既に hard_reject 済みは winner 候補にならない
    records = [{"prompt": "p", "mode": "nothinking", "answer": str(i)} for i in range(3)]
    composites = [
        _comp(0.9, rubric=0.9, hard=["TRUNC"]),
        _comp(0.5, rubric=0.5),
        _comp(0.5, rubric=0.4),
    ]
    apply_best_of_n(records, composites, ["h0", "h1", "h2"], strategy="rubric_max")
    # 0 番は既に TRUNC なので除外。1/2 のうち 1 が勝者
    assert "TRUNC" in composites[0].hard_rejected_by
    assert BEST_OF_N_REJECTED not in composites[0].hard_rejected_by
    assert composites[1].hard_rejected_by == []
    assert BEST_OF_N_REJECTED in composites[2].hard_rejected_by


def test_apply_different_groups_independent():
    # 異なる prompt のグループは独立
    records = [
        {"prompt": "p1", "mode": "nothinking", "answer": "a"},
        {"prompt": "p1", "mode": "nothinking", "answer": "b"},
        {"prompt": "p2", "mode": "nothinking", "answer": "c"},
        {"prompt": "p2", "mode": "nothinking", "answer": "d"},
    ]
    composites = [
        _comp(0.1, rubric=0.1),
        _comp(0.9, rubric=0.9),
        _comp(0.5, rubric=0.5),
        _comp(0.7, rubric=0.7),
    ]
    apply_best_of_n(records, composites, ["h0", "h1", "h2", "h3"], strategy="rubric_max")
    assert BEST_OF_N_REJECTED in composites[0].hard_rejected_by
    assert composites[1].hard_rejected_by == []
    assert BEST_OF_N_REJECTED in composites[2].hard_rejected_by
    assert composites[3].hard_rejected_by == []


def test_apply_auto_falls_back_to_rubric_when_judge_none():
    records = [{"prompt": "p", "mode": "nothinking", "answer": str(i)} for i in range(2)]
    composites = [_comp(0.5, rubric=0.4), _comp(0.5, rubric=0.6)]
    apply_best_of_n(records, composites, ["h0", "h1"], strategy="auto", judge=None)
    assert composites[1].hard_rejected_by == []
    assert BEST_OF_N_REJECTED in composites[0].hard_rejected_by


def test_apply_singleton_group_keeps_winner():
    records = [{"prompt": "p", "mode": "nothinking", "answer": "x"}]
    composites = [_comp(0.5, rubric=0.5)]
    res = apply_best_of_n(records, composites, ["h0"], strategy="rubric_max")
    assert res[0].is_winner is True
    assert res[0].group_size == 1
