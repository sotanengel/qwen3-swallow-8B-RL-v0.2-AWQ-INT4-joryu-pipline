"""joryu-curate CLI のエンドツーエンドテスト (R-15 / R-19)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.cli import curate as cli
from joryu.curate.judge_client import RUBRIC_KEYS, FakeJudgeClient


def _make_input(tmp_path: Path) -> Path:
    src = tmp_path / "responses.jsonl"
    records = [
        {
            "prompt": "桜の特徴を3行で",
            "answer": (
                "桜は春に咲く日本の代表的な花で、薄いピンク色の花弁が特徴です。"
                "開花は地域によって異なり、北上していく様子は桜前線と呼ばれます。"
                "短い期間で散る儚さが古来から多くの和歌に詠まれてきました。"
            ),
            "mode": "nothinking",
            "sampling": {"temperature": 0.6, "top_p": 0.95},
            "system_prompt": "あなたは日本語アシスタントです。",
            "config_hash": "sha256-test",
            "style_id": "polite",
            "category": "国語",
        },
        {
            "prompt": "短い質問",
            "answer": "短",  # LEN-A で hard reject される想定
            "mode": "nothinking",
            "sampling": {"temperature": 0.6},
            "system_prompt": "",
            "config_hash": "sha256-test",
            "style_id": "polite",
            "category": "国語",
        },
    ]
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return src


def test_curate_cli_skip_llm_smoke(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    rc = cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"],
    )
    assert rc == 0
    assert (dst / "responses.high_quality.jsonl").exists()
    assert (dst / "responses.rejected.jsonl").exists()
    assert (dst / "scores.jsonl").exists()
    assert (dst / "curation_meta.json").exists()


def test_curate_cli_with_fake_judge(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    judge = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})

    rc = cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0"],
        _judge=judge,
    )
    assert rc == 0
    scores = (dst / "scores.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(scores) == 2
    # 第一段でハード棄却された 2 件目では judge は呼ばれない
    assert len(judge.calls) == 1


def test_curate_cli_writes_signal_versions_in_meta(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"],
    )
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert "LEN-A" in meta["signal_versions"]
    assert "LLM-RUBRIC" not in meta["signal_versions"]  # skip-llm
    assert meta["curate_config"]["fingerprints"]["signal_config_hash"].startswith("sha256-")


def test_curate_cli_missing_input_returns_error(tmp_path: Path) -> None:
    rc = cli.main(
        ["--src", str(tmp_path / "missing.jsonl"), "--dst", str(tmp_path / "out"), "--skip-llm"],
    )
    assert rc == 2


def test_curate_cli_schema_rejected_records_counted(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    src.write_text(
        json.dumps({"prompt": "only prompt"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    dst = tmp_path / "out"
    rc = cli.main(["--src", str(src), "--dst", str(dst), "--skip-llm"])
    assert rc == 0
    rej = (dst / "responses.rejected.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rej) == 1
    payload = json.loads(rej[0])
    assert "schema" in payload["rejected_by"]


@pytest.mark.parametrize("flag,value", [("--top-k", "1"), ("--keep-rate", "0.5")])
def test_curate_cli_selection_flags(tmp_path: Path, flag: str, value: str) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "out"
    rc = cli.main(["--src", str(src), "--dst", str(dst), flag, value, "--skip-llm"])
    assert rc == 0
