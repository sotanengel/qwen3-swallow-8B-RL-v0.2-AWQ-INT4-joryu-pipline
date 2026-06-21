"""joryu-stats: 蒸留 JSONL から dashboard 用の統計 JSON を生成する。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from joryu.config import Config, load_config
from joryu.stats import compute_stats

DEFAULT_CONFIG = "config.yaml"
DEFAULT_OUTPUT = "dashboard/public/stats.json"


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path) if cfg_path.exists() else Config()

    src = Path(args.input) if args.input else Path(cfg.distill.out_dir) / cfg.distill.out_file
    out = Path(args.output)

    stats = compute_stats(src)
    stats["_meta"] = {
        "source_path": str(src),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[joryu-stats] wrote {out}  (total={stats['total']})", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
