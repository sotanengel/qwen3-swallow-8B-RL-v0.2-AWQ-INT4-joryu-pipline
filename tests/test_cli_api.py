"""cli/api.py のテスト。"""

from __future__ import annotations

from joryu.cli.api import build_parser


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.repo_root == ""
