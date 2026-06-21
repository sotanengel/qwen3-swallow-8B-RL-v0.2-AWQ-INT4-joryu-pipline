"""CSV -> JSONL prompt bank 変換。元プロジェクトの `分野,プロンプト` 形式を取り込む。"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def csv_to_jsonl(src: str | Path, dst: str | Path) -> int:
    """`分野,プロンプト` CSV を 1 行 1 JSONL に変換し、書き出した行数を返す。"""
    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists():
        raise FileNotFoundError(f"source CSV not found: {src_p}")

    dst_p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    # utf-8-sig で BOM を自動除去
    with (
        src_p.open(encoding="utf-8-sig", newline="") as fin,
        dst_p.open("w", encoding="utf-8") as fout,
    ):
        reader = csv.DictReader(fin)
        for row in reader:
            prompt = (row.get("プロンプト") or "").strip()
            category = (row.get("分野") or "").strip()
            if not prompt:
                continue
            record: dict[str, str] = {"prompt": prompt}
            if category:
                record["category"] = category
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n
