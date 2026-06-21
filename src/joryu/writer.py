"""追記安全な JSONL writer。1 レコードごとに flush して resume 安全性を保つ。"""

from __future__ import annotations

import json
from pathlib import Path
from types import TracebackType
from typing import Any


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
            finally:
                self._fh.close()
                self._fh = None

    def write(self, record: dict[str, Any]) -> None:
        if self._fh is None:
            raise RuntimeError("JsonlAppendWriter must be used as a context manager")
        line = json.dumps(record, ensure_ascii=False)
        self._fh.write(line + "\n")
        self._fh.flush()
