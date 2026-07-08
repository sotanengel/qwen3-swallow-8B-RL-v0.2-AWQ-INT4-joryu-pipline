"""Bench 用プロンプトバンク生成/読み込み。

CI では GPU を使わず Fake クライアントで distill を回し、品質/スキーマ検証に使う。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from joryu.io.jsonl import iter_jsonl

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_COUNT = 50
DEFAULT_PROMPT_SEED = 42  # 生成ロジックの将来互換のため保持（現状は i 直番で決定）


def japanese_numeral(n: int) -> str:
    """1..50 を日本語の漢数字で返す。ベンチ用の簡易実装。"""
    if n < 1 or n > 50:
        raise ValueError(f"n out of range: {n} (expected 1..50)")
    units = {
        0: "",
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
    }
    if n == 10:
        return "十"
    if n <= 9:
        return units[n]
    if n < 20:
        return "十" + ("" if n == 10 else units[n - 10])
    if n < 30:
        return "二十" + ("" if n == 20 else units[n - 20])
    if n < 40:
        return "三十" + ("" if n == 30 else units[n - 30])
    if n < 50:
        return "四十" + ("" if n == 40 else units[n - 40])
    return "五十"


def default_prompt_text(i: int) -> str:
    numeral = japanese_numeral(i)
    return f"蒸留ベンチ用プロンプト{numeral}。三つの特徴を答えてください。"


def default_category(i: int) -> str:
    return "国語" if i % 2 == 0 else "数学"


def write_default_prompt_bank_jsonl(path: Path, *, count: int = DEFAULT_PROMPT_COUNT) -> None:
    """デフォルトのプロンプトバンクを書き出す（順序も決定的）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(1, count + 1):
            row = {"prompt": default_prompt_text(i), "category": default_category(i)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_prompt_bank_jsonl(path: Path) -> list[dict]:
    """プロンプトバンク JSONL を読み込む（検証用途）。"""
    rows = list(iter_jsonl(path, logger=logger, log_prefix="bench prompts"))
    if not rows:
        raise ValueError(f"empty prompt bank: {path}")
    return rows


__all__ = [
    "DEFAULT_PROMPT_COUNT",
    "DEFAULT_PROMPT_SEED",
    "japanese_numeral",
    "default_prompt_text",
    "default_category",
    "write_default_prompt_bank_jsonl",
    "read_prompt_bank_jsonl",
]
