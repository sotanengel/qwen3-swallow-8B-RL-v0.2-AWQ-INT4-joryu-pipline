"""抽出棄却レコードの蒸留元 JSONL 削除 (R-26)。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from joryu.curate.record_hash import compute_record_hash
from joryu.persistence.responses_store import load_records, write_records

logger = logging.getLogger(__name__)

__all__ = ["PurgeResult", "purge_rejected_from_source"]


@dataclass(frozen=True)
class PurgeResult:
    """蒸留元からの棄却レコード削除結果。"""

    purged: int
    not_found: int
    src_before: int
    src_after: int


def purge_rejected_from_source(src_path: Path, rejected_path: Path) -> PurgeResult:
    """`rejected_path` のレコードを `record_hash` で照合し、蒸留元 JSONL から削除する。"""
    src_records = load_records(src_path)
    src_before = len(src_records)

    if not rejected_path.is_file():
        return PurgeResult(purged=0, not_found=0, src_before=src_before, src_after=src_before)

    rejected_hashes: set[str] = set()
    for record in load_records(rejected_path):
        rejected_hashes.add(compute_record_hash(record))

    if not rejected_hashes:
        return PurgeResult(purged=0, not_found=0, src_before=src_before, src_after=src_before)

    src_hash_map = {compute_record_hash(record): record for record in src_records}
    purged = 0
    not_found = 0
    for rejected_hash in rejected_hashes:
        if rejected_hash in src_hash_map:
            del src_hash_map[rejected_hash]
            purged += 1
        else:
            not_found += 1
            logger.warning(
                "rejected record not found in distill source",
                extra={"record_hash": rejected_hash, "src_path": str(src_path)},
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
