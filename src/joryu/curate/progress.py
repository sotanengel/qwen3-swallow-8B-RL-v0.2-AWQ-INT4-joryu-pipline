"""curate 再開機能 (R-16)。

同一 `--dst` で中断されたランを再開できるよう、既存 `scores.jsonl` から
評価済み `record_hash` セットを抽出する。`CurateWriter` は既に append モードで
動作するため、ファイル末尾に書き足すだけで安全に再開できる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from joryu.io.jsonl import iter_jsonl

logger = logging.getLogger(__name__)


@dataclass
class ResumeState:
    """既存 `scores.jsonl` から復元した状態。

    - `evaluated_hashes`: 既に評価済みの record_hash 集合
    - `kept` / `rejected`: 直前ランで採用 / 棄却された件数 (writer の counter を補正)
    """

    evaluated_hashes: set[str]
    kept: int
    rejected: int

    @property
    def total(self) -> int:
        return self.kept + self.rejected


def load_resume_state(scores_jsonl: str | Path) -> ResumeState:
    """既存 `scores.jsonl` を 1 pass 走査して `ResumeState` を構築する。

    ファイル不在/空の場合は空集合を返す (= 完全新規ラン)。
    壊れた行はログ出力してスキップ。
    """
    p = Path(scores_jsonl)
    hashes: set[str] = set()
    kept = 0
    rejected = 0
    if not p.exists():
        return ResumeState(hashes, kept, rejected)
    try:
        for row in iter_jsonl(p, logger=logger, log_prefix="[curate.progress]"):
            rh = row.get("record_hash")
            if isinstance(rh, str) and rh:
                hashes.add(rh)
            if row.get("accepted"):
                kept += 1
            else:
                rejected += 1
    except OSError as exc:
        logger.warning("[curate.progress] %s の読み込みに失敗: %s", p, exc)
    return ResumeState(hashes, kept, rejected)


def clear_existing_outputs(dst_dir: str | Path) -> None:
    """`--no-resume` 用: 既存 `responses.high_quality.jsonl` / `responses.rejected.jsonl`
    / `scores.jsonl` を削除する (curation_meta.json は残す)。"""
    dst = Path(dst_dir)
    for name in ("responses.high_quality.jsonl", "responses.rejected.jsonl", "scores.jsonl"):
        p = dst / name
        if p.exists():
            p.unlink()


__all__ = [
    "ResumeState",
    "clear_existing_outputs",
    "load_resume_state",
]
