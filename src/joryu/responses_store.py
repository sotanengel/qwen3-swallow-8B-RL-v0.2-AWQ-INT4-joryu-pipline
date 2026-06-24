"""蒸留 JSONL の読み書き・レコード ID 生成・削除。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from joryu.dashboard_json import _atomic_write_text

RECORD_KEY_SEP = "\x1e"


def record_key(record: dict[str, Any]) -> str:
    """レコードの安定キー文字列 (dashboard jsonl.ts と同一)。"""
    return RECORD_KEY_SEP.join(
        [
            str(record.get("prompt", "")),
            str(record.get("category") or ""),
            str(record.get("mode") or ""),
            str(record.get("style_id") or ""),
            str(record.get("created_at") or ""),
            str(record.get("config_hash") or ""),
        ]
    )


def record_id(record: dict[str, Any]) -> str:
    """FNV-1a 32-bit ハッシュを base36 で返す (jsonl.ts recordId と同一)。"""
    hash_val = 2166136261
    text = record_key(record)
    for ch in text:
        hash_val ^= ord(ch)
        hash_val = (hash_val * 16777619) & 0xFFFFFFFF
    if hash_val == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    parts: list[str] = []
    n = hash_val
    while n:
        n, rem = divmod(n, 36)
        parts.append(digits[rem])
    return "".join(reversed(parts))


def load_records(path: Path) -> list[dict[str, Any]]:
    """JSONL を読み込み、有効行のみ返す。"""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            obj = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
            out.append(obj)
    return out


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    """レコード一覧を JSONL として原子的に書き出す。"""
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    text = "\n".join(lines)
    if text:
        text += "\n"
    _atomic_write_text(path, text)


def delete_record(path: Path, target_id: str) -> int:
    """指定 ID のレコードを 1 件削除。残件数を返す。見つからなければ KeyError。"""
    records = load_records(path)
    kept = [r for r in records if record_id(r) != target_id]
    if len(kept) == len(records):
        raise KeyError(target_id)
    write_records(path, kept)
    return len(kept)


def delete_all_records(path: Path) -> int:
    """全レコードを削除。削除件数を返す。"""
    records = load_records(path)
    deleted = len(records)
    write_records(path, [])
    return deleted
