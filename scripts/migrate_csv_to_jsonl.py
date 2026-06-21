"""元 CSV (分野,プロンプト) を joryu の JSONL prompt bank に変換する。

用法:
    uv run python scripts/migrate_csv_to_jsonl.py \\
        --src "C:/Users/.../make-japan-ai-great-again/src/mjaga/data/training_prompts.csv" \\
        --dst data/prompts/training_prompts.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from joryu.migrate import csv_to_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="元 CSV パス")
    parser.add_argument("--dst", required=True, type=Path, help="出力 JSONL パス")
    args = parser.parse_args(argv)

    n = csv_to_jsonl(args.src, args.dst)
    print(f"[migrate] {n} rows -> {args.dst}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
