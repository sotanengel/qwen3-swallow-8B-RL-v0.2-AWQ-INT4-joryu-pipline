"""curation.json の集計テスト (R-18)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.stats import compute_curation_stats, write_curation_json


def _score_row(**overrides):
    base = {
        "record_hash": "h",
        "final_score": 0.8,
        "accepted": True,
        "rejected_by": [],
        "signal_versions": {},
        "signal_scores": {},
        "signal_raw": {},
        "style_id": "polite",
    }
    base.update(overrides)
    return base


def _write(p: Path, rows: list[dict]) -> None:
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )


def test_compute_curation_stats_basic(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(final_score=0.9, accepted=True, style_id="polite"),
        _score_row(final_score=0.1, accepted=False, rejected_by=["LEN-A"], style_id="polite"),
        _score_row(
            final_score=0.3,
            accepted=False,
            rejected_by=["LEN-A", "LANG-JA"],
            style_id="casual",
        ),
    ]
    _write(src, rows)

    stats = compute_curation_stats(src)
    assert stats["total"] == 3
    assert stats["accepted"] == 1
    assert stats["rejected"] == 2
    assert stats["keep_rate"] == 1 / 3
    reasons = dict(stats["rejected_reasons_top"])
    assert reasons["LEN-A"] == 2
    assert reasons["LANG-JA"] == 1
    assert stats["by_style"]["polite"]["total"] == 2
    assert stats["by_style"]["polite"]["kept"] == 1


def test_compute_curation_stats_with_rubric(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(
            signal_raw={
                "LLM-RUBRIC": {
                    "accuracy": 5,
                    "completeness": 4,
                    "fluency": 5,
                    "instruction_following": 4,
                    "safety": 5,
                }
            },
        ),
        _score_row(
            signal_raw={
                "LLM-RUBRIC": {
                    "accuracy": 3,
                    "completeness": 2,
                    "fluency": 3,
                    "instruction_following": 2,
                    "safety": 3,
                }
            },
        ),
    ]
    _write(src, rows)
    stats = compute_curation_stats(src)
    assert stats["rubric_count"] == 2
    assert stats["rubric_avg"]["accuracy"] == 4.0


def test_compute_curation_stats_empty_file_returns_zero(tmp_path: Path) -> None:
    src = tmp_path / "missing.jsonl"
    stats = compute_curation_stats(src)
    assert stats["total"] == 0
    assert stats["accepted"] == 0


def test_write_curation_json_creates_file(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    _write(src, [_score_row()])
    dst = tmp_path / "curation.json"
    write_curation_json(src, dst)
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert payload["total"] == 1
    assert "_meta" in payload
