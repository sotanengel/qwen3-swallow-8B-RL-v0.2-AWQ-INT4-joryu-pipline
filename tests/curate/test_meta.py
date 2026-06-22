"""curation_meta.json のテスト (R-17)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.meta import compute_file_sha256, write_curation_meta


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
