"""joryu-probe-vllm: vLLM VRAM 上限プローブ CLI (Windows なら自動 Docker delegate)。"""

from __future__ import annotations

import argparse
import sys

from joryu.cli.common import add_config_argument
from joryu.docker_delegate import DEFAULT_IMAGE
from joryu.vllm_probe import run_vllm_probe


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-probe-vllm",
        description="vLLM の VRAM 上限をプローブし data/vllm_limits.json に書き出す。",
    )
    add_config_argument(p)
    p.add_argument(
        "--out",
        default="",
        help="出力 JSON パス (既定: config.model.limits_probe_file)",
    )
    p.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Docker イメージ (既定: {DEFAULT_IMAGE})",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--docker", action="store_true", help="常に Docker delegate を使う")
    g.add_argument("--no-docker", action="store_true", help="Docker delegate を無効化")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_vllm_probe(
        config=args.config,
        out=args.out or None,
        image=args.image,
        force_docker=args.docker,
        force_native=args.no_docker,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
