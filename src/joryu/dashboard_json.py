"""dashboard/public 向け JSON 書き出しの共通処理。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_dashboard_json(
    dst: Path,
    payload: dict[str, Any],
    *,
    source_path: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """統計 payload に `_meta` を付与して dashboard 用 JSON を書き出す。"""
    payload["_meta"] = {
        "source_path": str(source_path),
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
