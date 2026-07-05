"""curate 評価ループの逐次書き込みと SAMP-OUT 補正。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joryu.curate.progress import clear_existing_outputs
from joryu.curate.scoring import CompositeScore, SelectionResult
from joryu.curate.signals.stat import SAMP_OUT_CODE, apply_samp_out_filter
from joryu.curate.writer import CurateWriter

__all__ = [
    "StreamedCurateRow",
    "immediate_selection",
    "rewrite_curate_outputs",
    "samp_out_correct_rows",
    "uses_streaming_selection",
]


@dataclass
class StreamedCurateRow:
    record: dict[str, Any]
    composite: CompositeScore
    record_hash: str
    accepted: bool
    rejected_by: list[str]
    final_score: float


def uses_streaming_selection(
    *,
    best_of_n: str | None,
    top_k: int | None,
    keep_rate: float | None,
    cfg_top_k: int | None,
    cfg_keep_rate: float | None,
) -> bool:
    """グローバル選抜なしの逐次採否モードか。"""
    from joryu.curate.best_of_n import parse_strategy

    if parse_strategy(best_of_n) != "off":
        return False
    if top_k is not None or keep_rate is not None:
        return False
    return cfg_top_k is None and cfg_keep_rate is None


def immediate_selection(composite: CompositeScore, *, threshold: float) -> SelectionResult:
    """閾値のみで 1 件の採否を決める (グローバル選抜なし)。"""
    if composite.hard_rejected:
        return SelectionResult(False, composite.final_score, list(composite.hard_rejected_by))
    if composite.final_score >= threshold:
        return SelectionResult(True, composite.final_score, [])
    return SelectionResult(False, composite.final_score, ["BELOW_THRESHOLD"])


def row_from_selection(
    record: dict[str, Any],
    composite: CompositeScore,
    record_hash: str,
    selection: SelectionResult,
) -> StreamedCurateRow:
    return StreamedCurateRow(
        record=record,
        composite=composite,
        record_hash=record_hash,
        accepted=selection.accepted,
        rejected_by=list(selection.rejected_by),
        final_score=selection.final_score,
    )


def samp_out_correct_rows(
    rows: list[StreamedCurateRow],
    *,
    z_min: float,
    min_bucket_size: int,
) -> int:
    """SAMP-OUT を適用し、行の採否を in-place 更新する。戻り値 = 新規棄却件数。"""
    if not rows:
        return 0
    records = [r.record for r in rows]
    composites = [r.composite for r in rows]
    before = sum(1 for r in rows if r.accepted)
    added = apply_samp_out_filter(
        records,
        composites,
        z_min=z_min,
        min_bucket_size=min_bucket_size,
    )
    for row, comp in zip(rows, composites, strict=True):
        if SAMP_OUT_CODE in comp.hard_rejected_by:
            row.accepted = False
            row.rejected_by = list(comp.hard_rejected_by)
            row.final_score = comp.final_score
    after = sum(1 for r in rows if r.accepted)
    if added > 0 and after < before:
        return before - after
    return added


def rewrite_curate_outputs(dst: Path, rows: list[StreamedCurateRow]) -> None:
    """SAMP-OUT 補正後に scores / high_quality / rejected を再生成する。"""
    clear_existing_outputs(dst)
    with CurateWriter(dst) as writer:
        for row in rows:
            comp = row.composite
            writer.write(
                row.record,
                accepted=row.accepted,
                final_score=row.final_score,
                rejected_by=row.rejected_by,
                signal_versions=comp.signal_versions,
                signal_scores=comp.signal_scores,
                signal_raw=comp.signal_raw,
                record_hash=row.record_hash,
            )
