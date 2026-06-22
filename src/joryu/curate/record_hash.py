"""レコード単位のキャッシュキー (R-21)。

`record_hash = sha256(prompt || answer || mode || sampling || system_prompt || config_hash)`

- 同一レコードを入力 JSONL のファイル位置に依存せず確定する
- thinking モードでは `thinking_trace` も連結対象 (思考が違えば別レコード)
- 差分実行キャッシュ (R-20) の参照キーとして本 PR でも `scores.jsonl` に書き出すが、
  実際のキャッシュ参照ロジックは後続 PR で実装する。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def compute_record_hash(record: dict[str, Any]) -> str:
    """レコードから安定した record_hash を計算する。"""
    payload = {
        "prompt": record.get("prompt", ""),
        "answer": record.get("answer", ""),
        "mode": record.get("mode", ""),
        "sampling": _normalize(record.get("sampling", {})),
        "system_prompt": record.get("system_prompt", ""),
        "config_hash": record.get("config_hash", ""),
    }
    if record.get("mode") == "thinking":
        payload["thinking_trace"] = record.get("thinking_trace", "") or record.get("reasoning", "")
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()
