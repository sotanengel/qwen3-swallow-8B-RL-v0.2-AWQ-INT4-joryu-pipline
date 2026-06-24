"""既存 JSONL から処理済み run キーの集合を返す resume-safe ヘルパ。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from joryu.io.jsonl import iter_jsonl
from joryu.truncation import record_looks_truncated


def _round_float(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def run_key_from_parts(
    *,
    prompt: str,
    style_id: str | None,
    mode: str | None,
    temperature: Any,
    top_p: Any,
    tools_hash: str | None = None,
) -> str:
    """蒸留 run の安定キー（prompt + style + mode + sampling 主要軸 + tools）。"""
    payload = {
        "prompt": prompt,
        "style_id": style_id,
        "mode": mode,
        "temperature": _round_float(temperature),
        "top_p": _round_float(top_p),
    }
    if tools_hash is not None:
        payload["tools_hash"] = tools_hash
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def run_key_from_record(record: dict[str, Any]) -> str | None:
    """出力 JSONL レコードから run キーを構築。prompt 欠損時は None。"""
    prompt = record.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    sampling = record.get("sampling") or {}
    if not isinstance(sampling, dict):
        sampling = {}
    style_id = record.get("style_id")
    if style_id is not None and not isinstance(style_id, str):
        style_id = None
    mode = record.get("mode")
    if mode is not None and not isinstance(mode, str):
        mode = None
    return run_key_from_parts(
        prompt=prompt,
        style_id=style_id,
        mode=mode,
        temperature=sampling.get("temperature"),
        top_p=sampling.get("top_p"),
    )


def load_done_keys(path: str | Path) -> set[str]:
    """JSONL レコードから処理済 run キーの set を構築する。

    同一キーの最新レコードが途中打ち切りの場合は未処理扱いとする。
    """
    latest: dict[str, dict[str, Any]] = {}
    for record in iter_jsonl(Path(path)):
        key = run_key_from_record(record)
        if key is not None:
            latest[key] = record
    return {key for key, record in latest.items() if not record_looks_truncated(record)}


def load_truncated_run_keys(path: str | Path) -> set[str]:
    """途中打ち切りと判定されたレコードの run キーを返す。"""
    keys: set[str] = set()
    for record in iter_jsonl(Path(path)):
        if not record_looks_truncated(record):
            continue
        key = run_key_from_record(record)
        if key is not None:
            keys.add(key)
    return keys


def load_done_prompts(path: str | Path) -> set[str]:
    """後方互換: prompt 文字列のみの処理済集合（非推奨）。"""
    done: set[str] = set()
    for record in iter_jsonl(Path(path)):
        prompt = record.get("prompt")
        if isinstance(prompt, str) and prompt:
            done.add(prompt)
    return done
