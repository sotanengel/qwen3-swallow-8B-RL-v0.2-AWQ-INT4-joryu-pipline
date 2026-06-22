"""curate resume 機能テスト (R-16)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.progress import (
    ResumeState,
    clear_existing_outputs,
    load_resume_state,
)


def _write_scores(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )


def test_load_resume_state_missing_file(tmp_path: Path) -> None:
    state = load_resume_state(tmp_path / "no.jsonl")
    assert state.evaluated_hashes == set()
    assert state.kept == 0
    assert state.rejected == 0


def test_load_resume_state_collects_hashes_and_counts(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(
        p,
        [
            {"record_hash": "h1", "accepted": True},
            {"record_hash": "h2", "accepted": False},
            {"record_hash": "h3", "accepted": False},
        ],
    )
    state = load_resume_state(p)
    assert state.evaluated_hashes == {"h1", "h2", "h3"}
    assert state.kept == 1
    assert state.rejected == 2
    assert state.total == 3


def test_load_resume_state_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    p.write_text(
        '{"record_hash":"h1","accepted":true}\nnot json\n{"record_hash":"h2","accepted":false}\n',
        encoding="utf-8",
    )
    state = load_resume_state(p)
    assert state.evaluated_hashes == {"h1", "h2"}


def test_load_resume_state_handles_missing_record_hash(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(p, [{"accepted": True}, {"record_hash": "h2", "accepted": False}])
    state = load_resume_state(p)
    assert state.evaluated_hashes == {"h2"}
    assert state.kept == 1


def test_clear_existing_outputs_removes_three_files_only(tmp_path: Path) -> None:
    (tmp_path / "responses.high_quality.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "responses.rejected.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "scores.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "curation_meta.json").write_text("keep me", encoding="utf-8")
    clear_existing_outputs(tmp_path)
    assert not (tmp_path / "responses.high_quality.jsonl").exists()
    assert not (tmp_path / "responses.rejected.jsonl").exists()
    assert not (tmp_path / "scores.jsonl").exists()
    # meta は残る
    assert (tmp_path / "curation_meta.json").exists()


def test_resume_state_dataclass_fields():
    s = ResumeState(evaluated_hashes={"a"}, kept=3, rejected=2)
    assert s.total == 5
