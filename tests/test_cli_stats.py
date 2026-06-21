"""cli/stats.py: joryu-stats の引数パースと dashboard JSON 書き出し。"""

from __future__ import annotations

import json
from pathlib import Path

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
