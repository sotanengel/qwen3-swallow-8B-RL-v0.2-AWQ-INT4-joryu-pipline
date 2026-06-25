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
        "style_id": "prose",
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
        _score_row(final_score=0.9, accepted=True, style_id="prose"),
        _score_row(final_score=0.1, accepted=False, rejected_by=["LEN-A"], style_id="prose"),
        _score_row(
            final_score=0.3,
            accepted=False,
            rejected_by=["LEN-A", "LANG-JA"],
            style_id="dialog",
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
    assert stats["by_style"]["prose"]["total"] == 2
    assert stats["by_style"]["prose"]["kept"] == 1


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


# ---------- R-18 残要素 (by_sampling / by_sampling_style / by_mode / rejected_samples) ----------


def test_compute_curation_stats_by_sampling(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(
            sampling={"temperature": 0.6, "top_p": 0.95},
            accepted=True,
            style_id="prose",
        ),
        _score_row(
            sampling={"temperature": 0.6, "top_p": 0.95},
            accepted=False,
            rejected_by=["LEN-A"],
            style_id="prose",
        ),
        _score_row(
            sampling={"temperature": 0.9, "top_p": 0.8},
            accepted=True,
            style_id="dialog",
        ),
    ]
    _write(src, rows)
    stats = compute_curation_stats(src)
    assert "t=0.6,p=0.95" in stats["by_sampling"]
    assert stats["by_sampling"]["t=0.6,p=0.95"]["total"] == 2
    assert stats["by_sampling"]["t=0.6,p=0.95"]["kept"] == 1
    assert stats["by_sampling"]["t=0.9,p=0.8"]["keep_rate"] == 1.0


def test_compute_curation_stats_by_sampling_style_cells(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(
            sampling={"temperature": 0.6, "top_p": 0.95},
            accepted=True,
            style_id="prose",
        ),
        _score_row(
            sampling={"temperature": 0.6, "top_p": 0.95},
            accepted=False,
            rejected_by=["LEN-A"],
            style_id="dialog",
        ),
    ]
    _write(src, rows)
    stats = compute_curation_stats(src)
    cells = stats["by_sampling_style"]
    assert isinstance(cells, list)
    matched = {(c["sampling"], c["style_id"]): c for c in cells}
    assert matched[("t=0.6,p=0.95", "prose")]["kept"] == 1
    assert matched[("t=0.6,p=0.95", "dialog")]["kept"] == 0


def test_compute_curation_stats_by_mode(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(mode="thinking", final_score=0.9, accepted=True),
        _score_row(mode="thinking", final_score=0.2, accepted=False, rejected_by=["TRUNC"]),
        _score_row(mode="nothinking", final_score=0.7, accepted=True),
    ]
    _write(src, rows)
    stats = compute_curation_stats(src)
    assert stats["by_mode"]["thinking"]["total"] == 2
    assert stats["by_mode"]["nothinking"]["total"] == 1
    # mode 別 score_bins が存在
    assert isinstance(stats["by_mode"]["thinking"]["score_bins"], list)


def test_rejected_samples_deterministic_with_seed(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(
            record_hash=f"h{i}",
            prompt=f"prompt {i}",
            accepted=False,
            rejected_by=["LEN-A"],
        )
        for i in range(10)
    ]
    _write(src, rows)
    stats1 = compute_curation_stats(src, rejected_sample_n=5)
    stats2 = compute_curation_stats(src, rejected_sample_n=5)
    # 同一 seed なので決定的
    hashes1 = [s["record_hash"] for s in stats1["rejected_samples"]]
    hashes2 = [s["record_hash"] for s in stats2["rejected_samples"]]
    assert hashes1 == hashes2
    assert len(stats1["rejected_samples"]) == 5


def test_rejected_samples_excludes_accepted(tmp_path: Path) -> None:
    src = tmp_path / "scores.jsonl"
    rows = [
        _score_row(record_hash="acc", accepted=True),
        _score_row(record_hash="rej", accepted=False, rejected_by=["LEN-A"]),
    ]
    _write(src, rows)
    stats = compute_curation_stats(src, rejected_sample_n=5)
    hashes = [s["record_hash"] for s in stats["rejected_samples"]]
    assert "acc" not in hashes
    assert "rej" in hashes


def test_empty_stats_includes_new_fields() -> None:
    # ファイル不在時のフォールバック構造に新フィールドが含まれている
    stats = compute_curation_stats("/nonexistent.jsonl")
    assert "by_sampling" in stats
    assert "by_sampling_style" in stats
    assert "by_mode" in stats
    assert "rejected_samples" in stats
