"""screening stats のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.stats import compute_screening_stats, write_screening_json


def test_compute_screening_stats(tmp_path: Path):
    scores = tmp_path / "scores.jsonl"
    row = {
        "screening_label": "REVIEW",
        "final_score": 0.5,
        "rejected_by": [],
        "signal_scores": {"LLM-HEALTH": 0.8, "END-WELL": 1.0},
        "signal_raw": {
            "LLM-HEALTH": {
                "L-01": 4,
                "L-02": 3,
                "L-03": 4,
                "L-04": 4,
                "L-05": 3,
                "reason_brief": "ok",
            }
        },
        "evaluator_model": "Llama-3.1-Swallow-8B-Instruct-v0.5",
    }
    scores.write_text(json.dumps(row) + "\n", encoding="utf-8")
    stats = compute_screening_stats(scores)
    assert stats["total"] == 1
    assert stats["label_distribution"]["REVIEW"]["count"] == 1
    assert stats["llm_health_averages"]["L-01"] == 4.0


def test_write_screening_json(tmp_path: Path):
    scores = tmp_path / "scores.jsonl"
    scores.write_text(
        json.dumps({"screening_label": "OK", "final_score": 0.9, "rejected_by": []}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "screening.json"
    data = write_screening_json(scores, out)
    assert data["total"] == 1
    assert out.exists()
