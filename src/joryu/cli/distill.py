"""joryu-distill: 蒸留 CLI (Windows なら自動 Docker delegate)。"""

from __future__ import annotations

import argparse
import re
import sys
import time

from joryu.config import load_config
from joryu.distill import run_distill
from joryu.docker_delegate import DEFAULT_IMAGE, run_in_docker, should_use_docker
from joryu.vllm_client import SupportsChat

DEFAULT_CONFIG = "config.yaml"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-distill",
        description="Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4 で JSONL prompt bank を蒸留する。",
    )
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"設定ファイル (既定: {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "--bank",
        default="",
        help="prompt bank JSONL (既定: config.distill.prompt_bank)",
    )
    p.add_argument(
        "--out",
        default="",
        help="出力 JSONL (既定: config.distill.out_dir/out_file)",
    )
    p.add_argument("--count", type=int, default=0, help="新規生成件数 (0 = 全件)")
    p.add_argument("--duration", default="", help="実行時間上限 (例: 2h, 30m, 1h30m)")
    p.add_argument(
        "--mode",
        choices=("thinking", "nothinking"),
        default=None,
        help="行に mode が無い場合の既定モード (config.model.mode を上書き)",
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


_DURATION_RE = re.compile(r"(\d+)\s*(h|m|s)")


def parse_duration(text: str | None) -> int | None:
    """`2h`, `30m`, `45s`, `1h30m` などを秒数に変換。空/None は None。"""
    if not text:
        return None
    total = 0
    found = False
    for match in _DURATION_RE.finditer(text):
        found = True
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        else:
            total += value
    if not found:
        raise ValueError(f"could not parse duration: {text!r}")
    return total


def _docker_extra_args(args: argparse.Namespace) -> list[str]:
    out: list[str] = ["--count", str(args.count)]
    if args.duration:
        out.extend(["--duration", args.duration])
    if args.bank:
        out.extend(["--bank", args.bank])
    if args.out:
        out.extend(["--out", args.out])
    if args.mode:
        out.extend(["--mode", args.mode])
    return out


def main(argv: list[str] | None = None, *, _client: SupportsChat | None = None) -> int:
    args = build_parser().parse_args(argv)

    if should_use_docker(force_docker=args.docker, force_native=args.no_docker):
        return run_in_docker(
            image=args.image,
            config=args.config,
            extra_args=_docker_extra_args(args),
        )

    cfg = load_config(args.config)
    if args.mode is not None:
        cfg.model.mode = args.mode

    deadline = None
    secs = parse_duration(args.duration)
    if secs is not None:
        deadline = time.time() + secs

    bank = args.bank or None
    out = args.out or None
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=_client,
        count=args.count,
        deadline=deadline,
    )
    print(f"[joryu-distill] wrote {n} records", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
