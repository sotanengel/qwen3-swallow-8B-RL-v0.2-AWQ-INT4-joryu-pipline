"""seed-gen CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_cli_parser_defaults() -> None:
    from joryu.seed_gen.cli import build_parser

    args = build_parser().parse_args([])
    assert args.mode == "create"
    assert args.resume is False


def test_cli_parser_check_mode() -> None:
    from joryu.seed_gen.cli import build_parser

    args = build_parser().parse_args(["--mode", "check"])
    assert args.mode == "check"


def test_cli_parser_rejects_removed_flags() -> None:
    from joryu.seed_gen.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--fake-llm"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--dry-run"])


def test_cli_check_mode_no_bank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check モードで bank が存在しないとき exit 0 を返す (nothing to check)。"""
    monkeypatch.chdir(tmp_path)
    domains = Path(__file__).resolve().parents[2] / "src/joryu/seed_gen/domains.yaml"
    from joryu.seed_gen.cli import main

    rc = main(
        [
            "--mode",
            "check",
            "--domains-config",
            str(domains),
            "--bank",
            str(tmp_path / "empty.jsonl"),
            "--state",
            str(tmp_path / "state.json"),
        ]
    )
    assert rc == 0
