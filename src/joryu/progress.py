"""既存 JSONL から処理済 prompt の集合を返す resume-safe ヘルパ。"""

from __future__ import annotations

import json
from pathlib import Path


def load_done_prompts(path: str | Path) -> set[str]:
    """`prompt` フィールドを持つ JSONL レコードから set を構築する。"""
    p = Path(path)
    if not p.exists():
        return set()
    done: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        prompt = record.get("prompt")
        if isinstance(prompt, str) and prompt:
            done.add(prompt)
    return done
