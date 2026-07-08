"""joryu-curate CLI: 棄却レコードの蒸留元自動削除 (R-26)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.cli import curate as cli
from joryu.persistence.progress import load_done_keys
from joryu.persistence.responses_store import load_records


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
            "style_id": "prose",
            "category": "国語",
        },
        {
            "prompt": "短い質問",
            "answer": "短",
            "mode": "nothinking",
            "sampling": {"temperature": 0.6, "top_p": 0.95},
            "system_prompt": "",
            "config_hash": "sha256-test",
            "style_id": "prose",
            "category": "国語",
        },
    ]
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return src


def test_curate_cli_purges_rejected_from_source_by_default(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    rc = cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"],
    )
    assert rc == 0
    remaining = load_records(src)
    assert len(remaining) == 1
    assert remaining[0]["prompt"] == "桜の特徴を3行で"
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta["incremental"]["purge"]["enabled"] is True
    assert meta["incremental"]["purge"]["purged"] == 1


def test_curate_cli_no_purge_rejected_keeps_source(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    rc = cli.main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--threshold",
            "0.0",
            "--skip-llm",
            "--no-purge-rejected",
        ],
    )
    assert rc == 0
    assert len(load_records(src)) == 2
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta["incremental"]["purge"]["enabled"] is False
    assert meta["incremental"]["purge"]["purged"] == 0


def test_curate_cli_purge_frees_done_keys(tmp_path: Path) -> None:
    src = _make_input(tmp_path)
    dst = tmp_path / "curated"
    before_keys = load_done_keys(src)
    assert len(before_keys) == 2
    cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"],
    )
    after_keys = load_done_keys(src)
    assert len(after_keys) == 1
