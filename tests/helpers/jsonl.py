"""テスト用 JSONL ヘルパ。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.io.jsonl import iter_jsonl


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """dict 行リストを JSONL ファイルに書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    """JSONL ファイルを dict リストとして読み込む。"""
    return list(iter_jsonl(path))
