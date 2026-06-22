"""CurateWriter のテスト (R-14)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.writer import CurateWriter


def _rec(answer: str = "a") -> dict:
    return {
        "prompt": "p",
        "answer": answer,
        "mode": "nothinking",
        "sampling": {},
        "config_hash": "h",
    }


def test_writer_creates_three_files(tmp_path: Path) -> None:
    with CurateWriter(tmp_path) as w:
        w.write(
            _rec("kept"),
            accepted=True,
            final_score=0.9,
            rejected_by=[],
            signal_versions={"LEN-A": "v1"},
            signal_scores={"LEN-A": 1.0},
            signal_raw={"LEN-A": 100},
            record_hash="sha256-aa",
        )
        w.write(
            _rec("rejected"),
            accepted=False,
            final_score=0.1,
            rejected_by=["LEN-A"],
            signal_versions={"LEN-A": "v1"},
            signal_scores={"LEN-A": 0.0},
            signal_raw={"LEN-A": 0},
            record_hash="sha256-bb",
        )

    high = tmp_path / "responses.high_quality.jsonl"
    rej = tmp_path / "responses.rejected.jsonl"
    scores = tmp_path / "scores.jsonl"
    assert high.exists() and rej.exists() and scores.exists()

    high_lines = high.read_text(encoding="utf-8").strip().splitlines()
    assert len(high_lines) == 1
    rec = json.loads(high_lines[0])
    assert rec["answer"] == "kept"

    rej_lines = rej.read_text(encoding="utf-8").strip().splitlines()
    assert len(rej_lines) == 1
    rej_rec = json.loads(rej_lines[0])
    assert rej_rec["rejected_by"] == ["LEN-A"]

    score_lines = scores.read_text(encoding="utf-8").strip().splitlines()
    assert len(score_lines) == 2


def test_writer_counts_match(tmp_path: Path) -> None:
    with CurateWriter(tmp_path) as w:
        for i in range(5):
            w.write(
                _rec(str(i)),
                accepted=(i % 2 == 0),
                final_score=0.5,
                rejected_by=[] if i % 2 == 0 else ["X"],
                signal_versions={},
                signal_scores={},
                signal_raw={},
                record_hash=f"r{i}",
            )
    assert w.kept == 3
    assert w.rejected == 2
    assert w.total == 5


def test_writer_flushes_each_record(tmp_path: Path) -> None:
    # context を抜けずに途中で出力ファイルを読んでも書かれていること。
    with CurateWriter(tmp_path) as w:
        w.write(
            _rec("first"),
            accepted=True,
            final_score=0.9,
            rejected_by=[],
            signal_versions={},
            signal_scores={},
            signal_raw={},
            record_hash="r0",
        )
        intermediate = (tmp_path / "responses.high_quality.jsonl").read_text(encoding="utf-8")
        assert "first" in intermediate
