"""cli/stats.py: joryu-stats の引数パースと dashboard JSON 書き出し。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.cli.stats import build_parser, main


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.config == "config.yaml"
    assert args.input == ""
    assert args.output == "dashboard/public/stats.json"


def test_main_writes_dashboard_json(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M", "mode": "thinking"}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "dashboard" / "public" / "stats.json"
    cfg = tmp_path / "c.yaml"
    cfg.write_text("model: {}\n", encoding="utf-8")
    rc = main(["--config", str(cfg), "--input", str(src), "--output", str(out)])
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["models"]["M"] == 1


def test_main_resolves_distill_input_relative_to_config_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API コンテナ (cwd≠repo_root) でも config 基準で JSONL を読める。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    jsonl = repo / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M", "mode": "thinking"}) + "\n",
        encoding="utf-8",
    )
    cfg = repo / "config.yaml"
    cfg.write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    out = repo / "dashboard" / "public" / "stats.json"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    rc = main(["--config", str(cfg), "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] == 1


def test_main_handles_missing_input_gracefully(tmp_path: Path) -> None:
    out = tmp_path / "stats.json"
    cfg = tmp_path / "c.yaml"
    cfg.write_text("distill:\n  out_dir: 'nowhere'\n  out_file: 'r.jsonl'\n", encoding="utf-8")
    rc = main(["--config", str(cfg), "--output", str(out)])
    # 入力が無くても空統計を書き出す
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] == 0
