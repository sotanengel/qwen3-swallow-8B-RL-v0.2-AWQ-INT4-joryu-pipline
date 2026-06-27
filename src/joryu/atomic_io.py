"""原子的ファイル書き込み。"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
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
            handle.flush()
            os.fsync(handle.fileno())
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
