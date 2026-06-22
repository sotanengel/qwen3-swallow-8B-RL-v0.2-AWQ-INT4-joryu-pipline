"""蒸留 JSONL (生 / `.zst`) のストリーミング読み込み (R-09)。

入力 JSONL は read-only オープンする。蒸留中の `JsonlAppendWriter` と並走しても破壊しない。
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import zstandard as zstd

logger = logging.getLogger(__name__)

REQUIRED_FIELDS: tuple[str, ...] = (
    "prompt",
    "answer",
    "mode",
    "sampling",
    "config_hash",
)


def _open_text(path: Path) -> io.TextIOBase:
    """JSONL / .jsonl.zst を utf-8 テキストモードで開く。"""
    if path.suffix == ".zst" or path.name.endswith(".jsonl.zst"):
        raw = path.open("rb")
        dctx = zstd.ZstdDecompressor()
        reader = dctx.stream_reader(raw)
        return io.TextIOWrapper(reader, encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_records(src: str | Path) -> Iterator[dict[str, Any]]:
    """JSONL をストリーミングで 1 行ずつ yield する。

    不正 JSON 行は warning ログを出してスキップする。
    schema 必須フィールドが欠落しているレコードはそのまま yield するが、
    `_schema_ok` フラグを False で付与し、下流で `rejected_by="schema"` 扱いにできる。
    """
    p = Path(src)
    if not p.exists():
        return
    with _open_text(p) as fh:
        for lineno, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("[curate.loader] skip malformed line %d: %s", lineno, exc)
                continue
            if not isinstance(rec, dict):
                logger.warning("[curate.loader] skip non-object line %d", lineno)
                continue
            rec["_schema_ok"] = all(rec.get(k) is not None for k in REQUIRED_FIELDS)
            yield rec


def count_records(src: str | Path) -> int:
    """事前にレコード数だけ知りたいとき (progress 用)。1 pass。"""
    return sum(1 for _ in iter_records(src))
