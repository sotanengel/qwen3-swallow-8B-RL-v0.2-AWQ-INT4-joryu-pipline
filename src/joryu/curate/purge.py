"""抽出棄却レコードの蒸留元 JSONL 削除 (R-26)。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joryu.curate.loader import normalize_record
from joryu.curate.record_hash import compute_record_hash
from joryu.io.jsonl import iter_jsonl
from joryu.persistence.responses_store import load_records, write_records

logger = logging.getLogger(__name__)

__all__ = ["PurgeResult", "purge_record_hash", "purge_rejected_from_source"]


@dataclass(frozen=True)
class PurgeResult:
    """蒸留元からの棄却レコード削除結果。"""

    purged: int
    not_found: int
    src_before: int
    src_after: int


def purge_record_hash(record: dict[str, Any]) -> str:
    """curate.loader と同じ正規化後に record_hash を計算する。"""
    normalized = dict(record)
    normalize_record(normalized)
    return compute_record_hash(normalized)


def _rejected_hashes_from_scores(scores_path: Path) -> set[str]:
    rejected: set[str] = set()
    for row in iter_jsonl(scores_path):
        if row.get("accepted") is not False:
            continue
        record_hash = row.get("record_hash")
        if isinstance(record_hash, str) and record_hash:
            rejected.add(record_hash)
    return rejected


def _rejected_hashes_from_jsonl(rejected_path: Path) -> set[str]:
    rejected: set[str] = set()
    for record in load_records(rejected_path):
        rejected.add(purge_record_hash(record))
    return rejected


def purge_rejected_from_source(
    src_path: Path,
    rejected_path: Path,
    *,
    scores_path: Path | None = None,
) -> PurgeResult:
    """棄却レコードを蒸留元 JSONL から削除する。

    照合は curate と同じ `record_hash` を使う。`scores.jsonl` があれば
    そこに記録済みの `record_hash` を優先する (mode 推論差分を避ける)。
    """
    src_records = load_records(src_path)
    src_before = len(src_records)
    src_hash_map = {purge_record_hash(record): record for record in src_records}

    rejected_hashes: set[str] = set()
    if scores_path is not None and scores_path.is_file():
        rejected_hashes = _rejected_hashes_from_scores(scores_path)
    if not rejected_hashes and rejected_path.is_file():
        rejected_hashes = _rejected_hashes_from_jsonl(rejected_path)

    if not rejected_hashes:
        return PurgeResult(purged=0, not_found=0, src_before=src_before, src_after=src_before)

    purged = 0
    not_found = 0
    for rejected_hash in rejected_hashes:
        if rejected_hash in src_hash_map:
            del src_hash_map[rejected_hash]
            purged += 1
        else:
            not_found += 1

    if not_found:
        logger.warning(
            "rejected records not found in distill source",
            extra={
                "not_found": not_found,
                "src_path": str(src_path),
                "rejected_path": str(rejected_path),
                "scores_path": str(scores_path) if scores_path else None,
            },
        )

    kept = list(src_hash_map.values())
    if purged > 0:
        write_records(src_path, kept)

    return PurgeResult(
        purged=purged,
        not_found=not_found,
        src_before=src_before,
        src_after=len(kept),
    )
