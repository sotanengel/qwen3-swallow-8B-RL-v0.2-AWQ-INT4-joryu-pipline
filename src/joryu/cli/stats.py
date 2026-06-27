"""joryu-stats: 蒸留 JSONL から dashboard 用の統計 JSON を生成する。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from joryu.cli.common import add_config_argument, resolve_cli_config, resolve_cli_distill_input
from joryu.curate.stats import DEFAULT_CURATION_OUTPUT, write_curation_json
from joryu.stats import DEFAULT_STATS_OUTPUT, write_stats_json

DEFAULT_OUTPUT = DEFAULT_STATS_OUTPUT

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-stats",
        description="蒸留 JSONL から dashboard 用統計 JSON を生成する。",
    )
    add_config_argument(p)
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
    cfg = resolve_cli_config(args)

    src = resolve_cli_distill_input(args, cfg)
    out = Path(args.output)

    stats = write_stats_json(src, out)
    logger.info("[joryu-stats] wrote %s  (total=%s)", out, stats["total"])

    if args.curation:
        curate_dir = Path(args.curation)
        scores = curate_dir / "scores.jsonl"
        if scores.exists():
            cur_out = Path(args.curation_output)
            cur = write_curation_json(scores, cur_out)
            logger.info(
                "[joryu-stats] wrote %s  (total=%s, kept=%s)",
                cur_out,
                cur["total"],
                cur["accepted"],
            )
        else:
            logger.warning("[joryu-stats] curation scores.jsonl missing: %s", scores)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
