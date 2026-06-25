"""cli/distill.py: 引数パース・duration パース・main ハッピーパス。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.cli.distill import build_parser, parse_duration


def test_parse_duration_hours() -> None:
    assert parse_duration("2h") == 7200


def test_parse_duration_minutes() -> None:
    assert parse_duration("30m") == 1800


def test_parse_duration_seconds() -> None:
    assert parse_duration("45s") == 45


def test_parse_duration_compound() -> None:
    assert parse_duration("1h30m") == 5400


def test_parse_duration_empty_returns_none() -> None:
    assert parse_duration("") is None
    assert parse_duration(None) is None  # type: ignore[arg-type]


def test_parse_duration_bad() -> None:
    with pytest.raises(ValueError):
        parse_duration("two hours")


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.config == "config.yaml"
    assert args.count == 0
    assert args.duration == ""
    assert args.docker is False
    assert args.no_docker is False
    assert args.bank == ""
    assert args.out == ""
    assert args.style == ""
    assert args.temperature == ""
    assert args.top_p == ""


def test_parser_style_and_sampling() -> None:
    args = build_parser().parse_args(
        ["--style", "prose,dialog", "--temperature", "0.5,0.8", "--top-p", "0.8,0.9"]
    )
    assert args.style == "prose,dialog"
    assert args.temperature == "0.5,0.8"
    assert args.top_p == "0.8,0.9"


def test_parser_no_longer_has_mode_arg() -> None:
    """`--mode` フラグは #94 で削除済み。指定すると argparse がエラー。"""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--mode", "thinking"])


def test_main_runs_native_with_fake_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bank = tmp_path / "bank.jsonl"
    bank.write_text(json.dumps({"prompt": "Q"}) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    cfg_yaml = tmp_path / "c.yaml"
    cfg_yaml.write_text(
        "distill:\n"
        f'  prompt_bank: "{bank.as_posix()}"\n'
        f'  out_dir: "{tmp_path.as_posix()}"\n'
        '  out_file: "out.jsonl"\n',
        encoding="utf-8",
    )
    (tmp_path / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")

    from joryu.cli import distill as cli_distill
    from tests.conftest import FakeVllmClient

    fake = FakeVllmClient(answer="ans", thinking="th")

    # native 経路 + fake client 注入
    rc = cli_distill.main(
        ["--no-docker", "--config", str(cfg_yaml), "--out", str(out)],
        _client=fake,
    )
    assert rc == 0
    assert out.exists()
    rec = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert rec["answer"] == "ans"


def test_main_invalid_style_returns_error(tmp_path: Path) -> None:
    from joryu.cli import distill as cli_distill

    cfg_yaml = tmp_path / "c.yaml"
    cfg_yaml.write_text('distill:\n  styles_file: "styles.yaml"\n', encoding="utf-8")
    rc = cli_distill.main(["--no-docker", "--config", str(cfg_yaml), "--style", "unknown"])
    assert rc == 2


def test_distill_job_spec_to_distill_argv_includes_style_and_sampling() -> None:
    from joryu.jobs.models import DistillJobSpec

    args = build_parser().parse_args(
        [
            "--style",
            "prose",
            "--temperature",
            "0.5,0.8",
            "--top-p",
            "0.9",
            "--count",
            "3",
        ]
    )
    spec = DistillJobSpec.from_cli_namespace(args)
    extra = spec.to_distill_argv()
    assert "--style" in extra
    assert "prose" in extra
    assert "--temperature" in extra
    assert "0.5,0.8" in extra
    assert "--top-p" in extra
    assert "0.9" in extra
    assert "--mode" not in extra
