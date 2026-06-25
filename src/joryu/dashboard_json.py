"""dashboard/public 向け JSON 書き出しの共通処理。"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _atomic_write_text(path: Path, text: str) -> None:
    """tmp → os.replace で原子的に書き出す (Windows の読み取り競合にも retry)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".tmp",
        prefix=f"{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        for attempt in range(10):
            try:
                os.replace(tmp_name, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


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
    _atomic_write_text(
        dst,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    return payload
