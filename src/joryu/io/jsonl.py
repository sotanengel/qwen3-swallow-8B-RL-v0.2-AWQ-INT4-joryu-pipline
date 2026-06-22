"""JSONL ストリーミング読み込みの共通実装。"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_jsonl(
    path: Path,
    *,
    logger: logging.Logger | None = None,
    log_prefix: str = "",
) -> Iterator[dict[str, Any]]:
    """JSONL を 1 行ずつ dict として yield する。

    - ファイル不存在: 何も yield しない
    - 空行: スキップ
    - JSON 解釈失敗 / 非 object: スキップ (logger 指定時は warning)
    """
    if not path.exists():
        return
    prefix = f"{log_prefix} " if log_prefix else ""
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                if logger is not None:
                    logger.warning("%sskip malformed line %d: %s", prefix, lineno, exc)
                continue
            if not isinstance(row, dict):
                if logger is not None:
                    logger.warning("%sskip non-object line %d", prefix, lineno)
                continue
            yield row
