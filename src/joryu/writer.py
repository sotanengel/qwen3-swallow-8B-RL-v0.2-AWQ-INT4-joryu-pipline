"""追記安全な JSONL writer。1 レコードごとに flush して resume 安全性を保つ。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import TracebackType
from typing import Any

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_jsonl_line(text: str) -> str:
    """改行と制御文字を JSONL 1 行として安全化する。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHARS.sub("", normalized)


def _sanitize_record(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_jsonl_line(value)
    if isinstance(value, dict):
        return {k: _sanitize_record(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_record(v) for v in value]
    return value


class JsonlAppendWriter:
    """`with` 構文で使うシンプルな追記 JSONL writer。

    - 親ディレクトリは存在しなければ作成
    - 1 レコードごとに `flush()` するため、中断しても直前まで保全される
    - `ensure_ascii=False` で日本語/絵文字をそのまま保存
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._fh: Any = None

    def __enter__(self) -> JsonlAppendWriter:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                os.fsync(self._fh.fileno())
            finally:
                self._fh.close()
                self._fh = None

    def write(self, record: dict[str, Any]) -> None:
        if self._fh is None:
            raise RuntimeError("JsonlAppendWriter must be used as a context manager")
        safe_record = _sanitize_record(record)
        line = json.dumps(safe_record, ensure_ascii=False)
        self._fh.write(line + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
