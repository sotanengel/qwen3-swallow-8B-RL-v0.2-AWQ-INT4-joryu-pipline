from __future__ import annotations

from joryu.cli.bench import _build_parser


def test_cli_bench_parser_smoke() -> None:
    parser = _build_parser()
    args = parser.parse_args(["throughput", "--fake", "--count", "1"])
    assert args.cmd == "throughput"
    assert args.fake is True
    assert args.count == 1
