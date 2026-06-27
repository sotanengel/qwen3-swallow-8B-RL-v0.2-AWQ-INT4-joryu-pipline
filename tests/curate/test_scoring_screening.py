"""健全性スクリーニング scoring のテスト。"""

from __future__ import annotations

from joryu.curate.scoring import (
    CompositeScore,
    apply_max_review_rate,
    label_screening_batch,
    screening_label,
)


def test_screening_label_ok():
    assert screening_label(0.8, ok_min=0.75, review_min=0.4) == "OK"


def test_screening_label_review():
    assert screening_label(0.5, ok_min=0.75, review_min=0.4) == "REVIEW"


def test_screening_label_ng():
    assert screening_label(0.2, ok_min=0.75, review_min=0.4) == "NG"


def test_apply_max_review_rate_demotes_low_scores():
    labels = ["REVIEW", "REVIEW", "REVIEW", "OK"]
    scores = [0.5, 0.6, 0.7, 0.9]
    out = apply_max_review_rate(labels, scores, max_rate=0.5)
    assert out.count("REVIEW") == 2
    assert out[0] == "NG"


def test_label_screening_batch_hard_reject_is_ng():
    comps = [
        CompositeScore(
            stat_score=0.0,
            llm_score=None,
            final_score=0.9,
            hard_rejected_by=["CTRL-CHAR"],
        )
    ]
    labels = label_screening_batch(comps, ok_min=0.75, review_min=0.4, max_review_rate=1.0)
    assert labels == ["NG"]
