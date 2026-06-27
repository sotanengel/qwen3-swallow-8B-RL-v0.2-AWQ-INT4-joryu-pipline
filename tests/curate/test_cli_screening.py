"""joryu-curate --screening CLI のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.cli.curate import main
from joryu.curate.judge_client import HEALTH_RUBRIC_KEYS, FakeJudgeClient


def _write_src(path: Path, n: int = 5) -> None:
    lines = []
    for i in range(n):
        lines.append(
            json.dumps(
                {
                    "prompt": f"質問{i}",
                    "answer": f"これは正常な回答です。番号{i}。",
                    "mode": "nothinking",
                    "config_hash": "h",
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_cli_screening_writes_three_files(tmp_path: Path, monkeypatch):
    src = tmp_path / "src.jsonl"
    dst = tmp_path / "out"
    _write_src(src, n=10)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
distill:
  out_dir: {tmp_path}
  out_file: src.jsonl
curate:
  out_dir: {dst}
""",
        encoding="utf-8",
    )
    judge = FakeJudgeClient(health_scores={k: 5 for k in HEALTH_RUBRIC_KEYS})
    monkeypatch.setenv("JORYU_CURATE_FAKE_JUDGE", "0")
    rc = main(
        [
            "--config",
            str(cfg),
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--screening",
            "--no-resume",
        ],
        _judge=judge,
    )
    assert rc == 0
    assert (dst / "screening.ok.jsonl").exists()
    assert (dst / "screening.review.jsonl").exists()
    assert (dst / "screening.ng.jsonl").exists()
    assert (dst / "scores.jsonl").exists()
