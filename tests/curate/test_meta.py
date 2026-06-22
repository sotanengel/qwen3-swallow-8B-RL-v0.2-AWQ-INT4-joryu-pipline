"""curation_meta.json のテスト (R-17)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.meta import (
    compute_file_sha256,
    format_incremental_summary,
    write_curation_meta,
)


def test_compute_file_sha256_stable(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    h1 = compute_file_sha256(p)
    h2 = compute_file_sha256(p)
    assert h1 is not None and h1.startswith("sha256-")
    assert h1 == h2


def test_compute_file_sha256_missing_returns_none(tmp_path: Path) -> None:
    assert compute_file_sha256(tmp_path / "missing") is None


def test_write_curation_meta_contains_required_fields(tmp_path: Path) -> None:
    src = tmp_path / "src.jsonl"
    src.write_text('{"prompt":"p"}\n', encoding="utf-8")
    dst = tmp_path / "curated"

    write_curation_meta(
        dst,
        src_path=src,
        input_records=10,
        kept=3,
        rejected=7,
        curate_fingerprints={
            "signal_config_hash": "sha256-s",
            "judge_config_hash": "sha256-j",
            "scoring_config_hash": "sha256-c",
        },
        judge_model="joryu",
        judge_mode="nothinking",
        signal_versions={"LEN-A": "v1", "LLM-RUBRIC": "v1"},
        cli_args={"threshold": 0.7},
        git_sha="abc123",
        llm_calls_total=2,
    )

    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta["source"]["sha256"] is not None
    assert meta["summary"] == {"kept": 3, "rejected": 7, "keep_rate": 0.3}
    assert meta["curate_config"]["fingerprints"]["signal_config_hash"] == "sha256-s"
    assert meta["signal_versions"]["LEN-A"] == "v1"
    assert meta["cli_args"] == {"threshold": 0.7}
    assert meta["git_sha"] == "abc123"
    assert meta["incremental"]["llm_calls_total"] == 2


def test_write_curation_meta_records_incremental_data(tmp_path: Path) -> None:
    src = tmp_path / "src.jsonl"
    src.write_text('{"prompt":"p"}\n', encoding="utf-8")
    dst = tmp_path / "curated"
    write_curation_meta(
        dst,
        src_path=src,
        input_records=100,
        kept=80,
        rejected=20,
        curate_fingerprints={
            "signal_config_hash": "s",
            "judge_config_hash": "j",
            "scoring_config_hash": "c",
        },
        judge_model="joryu",
        judge_mode="nothinking",
        signal_versions={},
        cli_args={},
        incremental={
            "input_records": 100,
            "cache_hits_full": 70,
            "cache_hits_partial": 10,
            "newly_evaluated": 20,
            "llm_calls_total": 15,
            "llm_calls_saved": 80,
            "cache_sources": ["/tmp/run1/scores.jsonl"],
        },
    )
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    inc = meta["incremental"]
    assert inc["cache_hits_full"] == 70
    assert inc["cache_hits_partial"] == 10
    assert inc["newly_evaluated"] == 20
    assert inc["llm_calls_total"] == 15
    assert inc["llm_calls_saved_vs_full_rerun"] == 80
    assert inc["cache_sources"] == ["/tmp/run1/scores.jsonl"]


def test_format_incremental_summary_contains_counters() -> None:
    text = format_incremental_summary(
        {
            "input_records": 1000,
            "cache_hits_full": 950,
            "cache_hits_partial": 30,
            "newly_evaluated": 20,
            "llm_calls_total": 5,
            "llm_calls_saved_vs_full_rerun": 945,
            "cache_sources": ["/tmp/run1/scores.jsonl"],
        }
    )
    assert "差分実行サマリ" in text
    assert "1000" in text
    assert "950" in text
    assert "/tmp/run1/scores.jsonl" in text
