"""cli/export.py: joryu-export の引数パースと main happy path。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.cli.export import build_parser, main


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.config == "config.yaml"
    assert args.input == ""
    assert args.out_dir == ""
    assert args.level == 0
    assert args.bundle_tar is False


def test_main_with_explicit_input(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "exports"
    cfg = tmp_path / "c.yaml"
    cfg.write_text('export:\n  out_dir: "unused"\n', encoding="utf-8")
    rc = main(
        [
            "--config",
            str(cfg),
            "--input",
            str(src),
            "--out-dir",
            str(out_dir),
            "--level",
            "3",
        ]
    )
    assert rc == 0
    # exports/<timestamp>/ ディレクトリが 1 つ作られている
    children = list(out_dir.iterdir())
    assert len(children) == 1
    assert (children[0] / "responses.jsonl.zst").exists()
    assert (children[0] / "meta.json").exists()
    assert (children[0] / "SHA256SUMS").exists()


def test_main_bundle_tar_flag(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M"}) + "\n", encoding="utf-8"
    )
    out_dir = tmp_path / "exp"
    cfg = tmp_path / "c.yaml"
    cfg.write_text('export:\n  out_dir: "unused"\n', encoding="utf-8")
    rc = main(
        ["--config", str(cfg), "--input", str(src), "--out-dir", str(out_dir), "--bundle-tar"]
    )
    assert rc == 0
    # tar は親ディレクトリ (out_dir) 直下に <timestamp>.tar として作られる
    tars = list(out_dir.glob("*.tar"))
    assert len(tars) == 1


def test_main_uses_config_defaults(tmp_path: Path) -> None:
    # config の distill.out_dir/out_file と export.out_dir のみを使う
    src = tmp_path / "data" / "distilled" / "responses.jsonl"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(json.dumps({"prompt": "P", "answer": "A"}) + "\n", encoding="utf-8")

    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "distill:\n"
        f'  out_dir: "{(tmp_path / "data" / "distilled").as_posix()}"\n'
        '  out_file: "responses.jsonl"\n'
        "export:\n"
        f'  out_dir: "{(tmp_path / "exp").as_posix()}"\n',
        encoding="utf-8",
    )
    rc = main(["--config", str(cfg)])
    assert rc == 0
    assert (tmp_path / "exp").exists()
    sub = next((tmp_path / "exp").iterdir())
    assert (sub / "responses.jsonl.zst").exists()


def test_main_missing_input_returns_error(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text("distill: {out_dir: 'nope', out_file: 'r.jsonl'}\n", encoding="utf-8")
    rc = main(["--config", str(cfg)])
    assert rc != 0
