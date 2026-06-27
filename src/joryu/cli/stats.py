"""joryu-stats: 蒸留 JSONL から dashboard 用の統計 JSON を生成する。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from joryu.cli.common import add_config_argument, resolve_cli_config, resolve_cli_distill_input
from joryu.curate.stats import (
    DEFAULT_CURATION_OUTPUT,
    DEFAULT_SCREENING_OUTPUT,
    write_curation_json,
    write_screening_json,
)
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
    p.add_argument(
        "--screening",
        action="store_true",
        help="screening.json も生成 (--curation 指定時)",
    )
    p.add_argument(
        "--screening-output",
        default="",
        help="screening.json の出力先 (既定: dashboard/public/screening.json)",
    )
    p.add_argument(
        "--screening-format",
        default="json",
        choices=["json", "csv"],
        help="screening レポート形式",
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
            if args.screening:
                scr_out = Path(args.screening_output or DEFAULT_SCREENING_OUTPUT)
                scr = write_screening_json(scores, scr_out)
                if args.screening_format == "csv":
                    _write_screening_csv(scr, scr_out.with_suffix(".csv"))
                logger.info(
                    "[joryu-stats] wrote %s  (total=%s)",
                    scr_out,
                    scr["total"],
                )
        else:
            logger.warning("[joryu-stats] curation scores.jsonl missing: %s", scores)
    return 0


def _write_screening_csv(stats: dict, path: Path) -> None:
    """screening 集計を CSV 1 行ヘッダ + ラベル行形式で出力。"""
    import csv

    rows: list[dict[str, str]] = []
    for lbl, bucket in (stats.get("label_distribution") or {}).items():
        rows.append(
            {
                "section": "label",
                "key": lbl,
                "count": str(bucket.get("count", 0)),
                "rate": str(bucket.get("rate", 0)),
            }
        )
    for rid, rate in (stats.get("rule_violation_rates") or {}).items():
        rows.append({"section": "rule", "key": rid, "count": "", "rate": str(rate)})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "key", "count", "rate"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
