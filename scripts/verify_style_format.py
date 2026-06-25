#!/usr/bin/env python3
"""styles.yaml 形式指示のローカル実測検証 (#55 サブタスク Y1/Y3)。

GPU + vLLM (または joryu-llm-serve) 環境で dialog/prose/口調プリセットの
markdown 率・文数を比較する。CI では実行しない。

用法:
  uv run python scripts/verify_style_format.py
  uv run python scripts/verify_style_format.py --input data/.verify-style/responses.jsonl
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from joryu.style_format import aggregate_by_style, check_style_format_criteria  # noqa: E402

VERIFY_PROMPTS = [
    {"prompt": "桜の特徴を教えてください", "category": "国語"},
    {"prompt": "1+1はいくつですか？", "category": "数学"},
    {"prompt": "日本の首都はどこですか？", "category": "地理"},
    {"prompt": "水はなぜ空に昇るのですか？", "category": "理科"},
    {"prompt": "敬語と丁寧語の違いは？", "category": "国語"},
    {"prompt": "100円の30%はいくら？", "category": "数学"},
    {"prompt": "富士山の標高は？", "category": "地理"},
    {"prompt": "光合成とは何ですか？", "category": "理科"},
    {"prompt": "「ありがとう」の英語は？", "category": "国語"},
    {"prompt": "週末の過ごし方を一つ教えて", "category": "生活"},
]

STYLES = ("dialog", "prose", "qa_short", "report")


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_prompt_bank(path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in VERIFY_PROMPTS:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_distill(*, work: Path, config: Path, bank: Path, out: Path) -> int:
    styles_arg = ",".join(STYLES)
    count = len(VERIFY_PROMPTS) * len(STYLES)
    cmd = [
        "uv",
        "run",
        "joryu-distill",
        "--no-docker",
        "--config",
        str(config),
        "--bank",
        str(bank),
        "--out",
        str(out),
        "--style",
        styles_arg,
        "--count",
        str(count),
    ]
    print(f"[verify-style] running: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd, cwd=ROOT)


def print_summary(aggregates: dict[str, dict[str, float]]) -> None:
    header = f"{'style_id':<10} {'count':>5} {'md_rate':>8} {'sent_avg':>9} {'char_avg':>9}"
    print(header, file=sys.stderr)
    print("-" * len(header), file=sys.stderr)
    for sid in STYLES:
        agg = aggregates.get(sid)
        if not agg:
            print(f"{sid:<10} {'—':>5} {'—':>8} {'—':>9} {'—':>9}", file=sys.stderr)
            continue
        print(
            f"{sid:<10} {int(agg['count']):>5} "
            f"{agg['md_marker_rate']:>8.2f} "
            f"{agg['mean_sentence_count']:>9.1f} "
            f"{agg['mean_char_count']:>9.0f}",
            file=sys.stderr,
        )


def check_criteria(aggregates: dict[str, dict[str, float]]) -> list[str]:
    """Y1/Y3 受け入れ基準。違反メッセージのリスト (空なら OK)。"""
    return check_style_format_criteria(aggregates)


def prepare_work_dir(work: Path) -> tuple[Path, Path, Path]:
    """検証用 work ディレクトリに bank/config/tools/styles を用意する。"""
    work.mkdir(parents=True, exist_ok=True)
    bank = work / "bank.jsonl"
    out_path = work / "responses.jsonl"
    cfg_path = work / "config.yaml"
    write_prompt_bank(bank)
    shutil.copy(ROOT / "tools.yaml", work / "tools.yaml")
    shutil.copy(ROOT / "styles.yaml", work / "styles.yaml")
    cfg_path.write_text(
        """distill:
  prompt_bank: "bank.jsonl"
  out_dir: "."
  out_file: "responses.jsonl"
  styles_file: "styles.yaml"
  tools_file: "tools.yaml"
""",
        encoding="utf-8",
    )
    return bank, cfg_path, out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify style format instructions (local GPU).")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config.yaml"),
        help="config YAML path",
    )
    parser.add_argument(
        "--input",
        default="",
        help="既存 responses.jsonl を分析のみ (distill をスキップ)",
    )
    parser.add_argument(
        "--work-dir",
        default="",
        help="作業ディレクトリ (既定: data/.verify-style)",
    )
    args = parser.parse_args(argv)

    if args.input:
        out_path = Path(args.input)
        if not out_path.is_file():
            print(f"[verify-style] error: input not found: {out_path}", file=sys.stderr)
            return 2
    else:
        work = Path(args.work_dir) if args.work_dir else ROOT / "data" / ".verify-style"
        bank, cfg_path, out_path = prepare_work_dir(work)
        if out_path.exists():
            out_path.unlink()
        rc = run_distill(work=work, config=cfg_path, bank=bank, out=out_path)
        if rc != 0:
            print(
                "[verify-style] distill failed (vLLM/GPU 未起動の可能性). "
                "joryu-llm-serve 起動後に再実行してください。",
                file=sys.stderr,
            )
            return rc

    records = load_jsonl(out_path)
    aggregates = aggregate_by_style(records)
    print(f"[verify-style] analyzed {len(records)} records from {out_path}", file=sys.stderr)
    if not records:
        print(
            "[verify-style] error: no records to analyze "
            "(vLLM/GPU 未起動または distill 失敗の可能性)",
            file=sys.stderr,
        )
        return 2
    print_summary(aggregates)

    errors = check_criteria(aggregates)
    if errors:
        for err in errors:
            print(f"[verify-style] FAIL: {err}", file=sys.stderr)
        return 1

    print("[verify-style] OK: Y1/Y3 criteria passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
