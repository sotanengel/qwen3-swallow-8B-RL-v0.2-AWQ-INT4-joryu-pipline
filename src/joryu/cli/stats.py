"""joryu-stats: 蒸留 JSONL から dashboard 用の統計 JSON を生成する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from joryu.config import Config, load_config
from joryu.curate.stats import DEFAULT_CURATION_OUTPUT, write_curation_json
from joryu.stats import DEFAULT_STATS_OUTPUT, write_stats_json

DEFAULT_CONFIG = "config.yaml"
DEFAULT_OUTPUT = DEFAULT_STATS_OUTPUT


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-stats",
        description="蒸留 JSONL から dashboard 用統計 JSON を生成する。",
    )
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"設定ファイル (既定: {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "--input",
        default="",
        help="入力 JSONL (既定: config.distill.out_dir/out_file)",
    )
    p.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"出力 JSON (既定: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--curation",
        default="",
        help="curate ラン dir (scores.jsonl を含む) を指定すると "
        f"{DEFAULT_CURATION_OUTPUT} も生成する",
    )
    p.add_argument(
        "--curation-output",
        default=DEFAULT_CURATION_OUTPUT,
        help=f"curation.json の出力先 (既定: {DEFAULT_CURATION_OUTPUT})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path) if cfg_path.exists() else Config()

    src = Path(args.input) if args.input else Path(cfg.distill.out_dir) / cfg.distill.out_file
    out = Path(args.output)

    stats = write_stats_json(src, out)
    print(f"[joryu-stats] wrote {out}  (total={stats['total']})", file=sys.stderr)

    if args.curation:
        curate_dir = Path(args.curation)
        scores = curate_dir / "scores.jsonl"
        if scores.exists():
            cur_out = Path(args.curation_output)
            cur = write_curation_json(scores, cur_out)
            print(
                f"[joryu-stats] wrote {cur_out}  (total={cur['total']}, kept={cur['accepted']})",
                file=sys.stderr,
            )
        else:
            print(f"[joryu-stats] curation scores.jsonl missing: {scores}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
