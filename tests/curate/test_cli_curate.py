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


def test_curate_cli_resume_skips_evaluated_records(tmp_path: Path) -> None:
    """同じ --dst で 2 回実行し、2 回目は --resume で 0 件再評価になる。"""
    src = _make_input(tmp_path)
    dst = tmp_path / "out"
    rc1 = cli.main(["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"])
    assert rc1 == 0
    first_meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    first_scores = (dst / "scores.jsonl").read_text(encoding="utf-8")

    rc2 = cli.main(["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"])
    assert rc2 == 0
    second_scores = (dst / "scores.jsonl").read_text(encoding="utf-8")
    # 全件 resume スキップなので scores.jsonl は変わらない
    assert first_scores == second_scores
    second_meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert second_meta["incremental"]["resume_skipped"] == first_meta["source"]["input_records"]


def test_curate_cli_no_resume_starts_fresh(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "out"
    cli.main(["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"])
    rc = cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm", "--no-resume"]
    )
    assert rc == 0
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta["incremental"]["resume_skipped"] == 0


def test_curate_cli_cache_from_reuses_signals(tmp_path: Path) -> None:
    """1 回目の出力を --cache-from で渡し、2 回目は LLM 呼び出しを完全削減できる。"""
    src = _make_input(tmp_path)
    dst1 = tmp_path / "run1"
    judge1 = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    cli.main(["--src", str(src), "--dst", str(dst1), "--threshold", "0.0"], _judge=judge1)
    first_calls = len(judge1.calls)
    assert first_calls > 0

    # 2 回目: 別 dst + --cache-from で 1 回目を参照、--no-resume で再評価強制
    dst2 = tmp_path / "run2"
    judge2 = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    cli.main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst2),
            "--threshold",
            "0.0",
            "--cache-from",
            str(dst1),
            "--no-resume",
        ],
        _judge=judge2,
    )
    # 全て full hit なので LLM は呼ばれない
    assert len(judge2.calls) == 0
    meta2 = json.loads((dst2 / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta2["incremental"]["cache_hits_full"] >= 1
    assert meta2["incremental"]["llm_calls_total"] == 0


def test_curate_cli_rescore_only_no_llm(tmp_path: Path) -> None:
    """--rescore-only で閾値だけ変えた再抽出が LLM 呼び出し 0 で完了する。"""
    src = _make_input(tmp_path)
    dst1 = tmp_path / "run1"
    judge1 = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    cli.main(["--src", str(src), "--dst", str(dst1), "--threshold", "0.0"], _judge=judge1)

    dst2 = tmp_path / "run2"
    judge2 = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    rc = cli.main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst2),
            "--threshold",
            "0.99",
            "--cache-from",
            str(dst1),
            "--no-resume",
            "--rescore-only",
        ],
        _judge=judge2,
    )
    assert rc == 0
    assert len(judge2.calls) == 0
    meta2 = json.loads((dst2 / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta2["incremental"]["llm_calls_total"] == 0


def test_curate_cli_best_of_n_rubric_max(tmp_path: Path) -> None:
    """同じ prompt で 3 バリアント → best-of-N rubric_max が 1 件だけ採用。"""
    src = tmp_path / "responses.jsonl"
    # DUP-GLOB 回避のため answer を意図的に変える (全件 stat 通過する想定)
    base = (
        "桜は春に咲く日本の代表的な花で、薄いピンク色の花弁が特徴です。"
        "開花は地域によって異なり、北上していく様子は桜前線と呼ばれます。"
        "短い期間で散る儚さが古来から多くの和歌に詠まれてきました。"
    )
    variants = [
        base,
        base + "また、桜餅などの春の和菓子にも欠かせません。",
        base + "夜桜のライトアップは観光地でも人気を集めています。",
    ]
    records = [
        {
            "prompt": "桜の特徴を3行で",
            "answer": variants[i],
            "mode": "nothinking",
            "sampling": {"temperature": t, "top_p": 0.95},
            "system_prompt": "",
            "config_hash": "h",
            "style_id": "polite",
        }
        for i, t in enumerate([0.4, 0.6, 0.9])
    ]
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    dst = tmp_path / "out"
    rc = cli.main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--threshold",
            "0.0",
            "--skip-llm",
            "--best-of-n",
            "rubric_max",
        ]
    )
    assert rc == 0
    # 2 件は BEST-OF-N で棄却される
    scores = [
        json.loads(line) for line in (dst / "scores.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    bon_rej = [s for s in scores if "BEST-OF-N" in (s.get("rejected_by") or [])]
    assert len(bon_rej) == 2


def test_curate_cli_minhash_index_persisted(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "out"
    cli.main(["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"])
    from joryu.curate.minhash_index import DEFAULT_INDEX_FILENAME

    assert (dst / DEFAULT_INDEX_FILENAME).exists()
