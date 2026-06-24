"""ダッシュボード recordId() と一致する record_key 生成。

dashboard/src/lib/jsonl.ts の recordKey / recordId と同一ロジック。
"""

from __future__ import annotations

from typing import Any

RECORD_KEY_SEP = "\x1e"


def record_key(record: dict[str, Any]) -> str:
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
    return _fnv1a_hash(record_key(record))


def _fnv1a_hash(text: str) -> str:
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return _to_base36(h)


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    parts: list[str] = []
    while n:
        n, rem = divmod(n, 36)
        parts.append(digits[rem])
    return "".join(reversed(parts))
