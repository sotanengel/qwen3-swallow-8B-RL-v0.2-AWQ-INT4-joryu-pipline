"""joryu-distill: 蒸留 CLI (Windows なら自動 Docker delegate)。"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from joryu.cli.common import add_config_argument
from joryu.config import load_config
from joryu.distill import default_stats_refresher, load_style_presets_from_config, run_distill
from joryu.docker_delegate import DEFAULT_IMAGE, run_in_docker, should_use_docker
from joryu.jobs.models import DistillJobSpec
from joryu.variants import parse_comma_list, parse_float_list, parse_modes
from joryu.vllm_client import SupportsChat


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-distill",
        description="Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4 で JSONL prompt bank を蒸留する。",
    )
    add_config_argument(p)
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
        default=None,
        help="推論モード (thinking / nothinking / auto)。カンマ区切りで直積スイープ可",
    )
    p.add_argument(
        "--style",
        default="",
        help="文体プリセット ID (カンマ区切り。styles.yaml 参照。例: polite,casual,expert)",
    )
    p.add_argument(
        "--temperature",
        default="",
        help="temperature スイープ (0.5〜1.0、カンマ区切り。例: 0.5,0.7,1.0)",
    )
    p.add_argument(
        "--top-p",
        default="",
        help="top_p スイープ (0.8〜0.95、カンマ区切り。例: 0.8,0.9,0.95)",
    )
    p.add_argument(
        "--tool-ids",
        default="",
        help="tool ID (カンマ区切り。行の tool_ids が空の行にのみ適用)",
    )
    p.add_argument(
        "--tool-loop",
        action="store_true",
        help="tool_call をローカル実行して再生成するループを有効化",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="tool_loop の最大ターン数 (既定: config.distill.tool_loop_max_turns)",
    )
    p.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Docker イメージ (既定: {DEFAULT_IMAGE})",
    )
    p.add_argument(
        "--redo-truncated",
        action="store_true",
        help="finish_reason=length またはヒューリスティックで打ち切りと判定された run を再蒸留",
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


def main(argv: list[str] | None = None, *, _client: SupportsChat | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = DistillJobSpec.from_cli_namespace(args)

    if should_use_docker(force_docker=args.docker, force_native=args.no_docker):
        return run_in_docker(
            image=args.image,
            config=spec.config,
            extra_args=spec.to_distill_argv(bank=args.bank, out=args.out),
        )

    try:
        cfg = load_config(spec.config)
        mode_sweep: list[str] | None = None
        if spec.mode is not None:
            parsed_modes = parse_modes(spec.mode)
            if parsed_modes is not None and len(parsed_modes) == 1:
                cfg.model.mode = parsed_modes[0]
            elif parsed_modes is not None and len(parsed_modes) > 1:
                mode_sweep = list(parsed_modes)

        style_presets = load_style_presets_from_config(cfg, spec.style)
        temperatures = parse_float_list(
            spec.temperature, min_val=0.5, max_val=1.0, name="temperature"
        )
        top_ps = parse_float_list(spec.top_p, min_val=0.8, max_val=0.95, name="top_p")
    except (FileNotFoundError, ValueError) as exc:
        print(f"[joryu-distill] error: {exc}", file=sys.stderr)
        return 2

    deadline = None
    try:
        secs = parse_duration(spec.duration)
    except ValueError as exc:
        print(f"[joryu-distill] error: {exc}", file=sys.stderr)
        return 2
    if secs is not None:
        deadline = time.time() + secs

    run_distill(
        cfg,
        bank_path=args.bank or None,
        out_path=args.out or None,
        client=_client,
        count=spec.count,
        deadline=deadline,
        redo_truncated=bool(getattr(args, "redo_truncated", False)),
        style_presets=style_presets or None,
        temperatures=temperatures,
        top_ps=top_ps,
        modes=mode_sweep,
        tool_loop=bool(getattr(args, "tool_loop", False)),
        tool_loop_max_turns=getattr(args, "max_turns", None),
        override_tool_ids=parse_comma_list(getattr(args, "tool_ids", "")) or None,
        config_path=Path(spec.config).resolve(),
        stats_refresher=default_stats_refresher,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
