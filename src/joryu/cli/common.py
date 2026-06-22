"""CLI 共通ヘルパ。"""

from __future__ import annotations

import argparse
from pathlib import Path

from joryu.config import Config
from joryu.paths import DEFAULT_CONFIG, resolve_distill_output, resolve_optional_config


def add_config_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str = DEFAULT_CONFIG,
) -> None:
    """--config 引数を parser に追加する。"""
    parser.add_argument(
        "--config",
        default=default,
        help=f"設定ファイル (既定: {default})",
    )


def resolve_cli_config(args: argparse.Namespace) -> Config:
    """args.config から Config を解決する (存在しなければ既定)。"""
    return resolve_optional_config(Path(args.config))


def resolve_cli_distill_input(args: argparse.Namespace, cfg: Config) -> Path:
    """stats/export 等: 蒸留 JSONL 入力パスを args.input から解決する。"""
    return resolve_distill_output(cfg, args.input or None)
