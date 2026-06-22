"""差分実行キャッシュ (R-20 / R-23)。

過去ランの `scores.jsonl` を読み込み、`record_hash` ごとに `signal_scores` /
`signal_versions` を保持する。新ランは

- `record_hash` 未知 → 全シグナル新規評価
- 全 version 一致 → LLM 含めて完全再利用
- 一部 version 不一致 → 該当シグナルだけ再計算 (本実装では「不一致シグナル群」だけを返す)
- `scoring_config_hash` のみ変化 → 合成スコアと採否のみ再計算 (`--rescore-only`)

の判定を高速に行うためのヘルパを提供する。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CachedRecord:
    """過去ランで評価済み 1 レコード分のスコアキャッシュ。"""

    record_hash: str
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_versions: dict[str, str] = field(default_factory=dict)
    signal_raw: dict[str, object] = field(default_factory=dict)
    final_score: float | None = None
    accepted: bool | None = None
    rejected_by: list[str] = field(default_factory=list)
    source: str = ""  # どの cache_from パス由来か


@dataclass
class CacheReuse:
    """1 レコードに対するキャッシュ再利用判定の結果。"""

    record_hash: str
    cached: CachedRecord | None
    reusable_signals: set[str]  # version 一致でそのままスコアを使えるシグナル
    stale_signals: set[str]  # version 不一致で再計算が必要なシグナル
    is_new_record: bool

    @property
    def is_full_hit(self) -> bool:
        """全シグナル一致 (= LLM 呼び出しゼロで採否再判定だけで済む)。"""
        return self.cached is not None and not self.stale_signals and not self.is_new_record

    @property
    def is_partial_hit(self) -> bool:
        """一部一致 (= stale_signals だけ再評価)。"""
        return self.cached is not None and bool(self.stale_signals) and not self.is_new_record


@dataclass
class CacheIndex:
    """`record_hash → CachedRecord` の辞書。複数 cache_from を merge 済み。"""

    records: dict[str, CachedRecord] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.records)

    def lookup(
        self,
        record_hash: str,
        *,
        expected_versions: dict[str, str],
    ) -> CacheReuse:
        cached = self.records.get(record_hash)
        if cached is None:
            return CacheReuse(record_hash, None, set(), set(expected_versions), True)
        reusable: set[str] = set()
        stale: set[str] = set()
        for code, version in expected_versions.items():
            cached_v = cached.signal_versions.get(code)
            if cached_v == version and code in cached.signal_scores:
                reusable.add(code)
            else:
                stale.add(code)
        return CacheReuse(record_hash, cached, reusable, stale, False)


def load_cache_index(paths: Iterable[Path | str]) -> CacheIndex:
    """複数 `scores.jsonl` をマージしてキャッシュインデックスを作る。

    マージ競合 (同一 `record_hash` で異なるスコア) は **後勝ち** で上書きする。
    呼び出し側が新しいパスを後ろに並べることで「新しいランの結果を優先」させる。
    """
    index = CacheIndex()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            p = p / "scores.jsonl"
        if not p.exists():
            logger.warning("[curate.cache] %s が存在しないのでスキップ", p)
            continue
        try:
            for row in _iter_rows(p):
                rh = row.get("record_hash")
                if not isinstance(rh, str) or not rh:
                    continue
                index.records[rh] = CachedRecord(
                    record_hash=rh,
                    signal_scores=dict(row.get("signal_scores") or {}),
                    signal_versions=dict(row.get("signal_versions") or {}),
                    signal_raw=dict(row.get("signal_raw") or {}),
                    final_score=_as_float(row.get("final_score")),
                    accepted=row.get("accepted") if isinstance(row.get("accepted"), bool) else None,
                    rejected_by=list(row.get("rejected_by") or []),
                    source=str(p),
                )
        except OSError as exc:
            logger.warning("[curate.cache] %s の読み込みに失敗: %s", p, exc)
            continue
        index.sources.append(str(p))
    return index


def _iter_rows(p: Path) -> Iterator[dict[str, object]]:
    with p.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _as_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def auto_detect_cache_paths(dst_root: Path, *, current_dst: Path) -> list[Path]:
    """`--cache-from` 未指定時のフォールバック: `dst_root` 直下の最新 `scores.jsonl` を 1 件採用。

    `current_dst` は除外 (同じランは参照しない)。
    """
    if not dst_root.exists() or not dst_root.is_dir():
        return []
    candidates: list[tuple[float, Path]] = []
    current_resolved = current_dst.resolve()
    for child in dst_root.iterdir():
        if not child.is_dir():
            continue
        if child.resolve() == current_resolved:
            continue
        scores = child / "scores.jsonl"
        if scores.exists():
            candidates.append((scores.stat().st_mtime, scores))
    if not candidates:
        return []
    candidates.sort(reverse=True)
    return [candidates[0][1]]


def merge_partial_signal_scores(
    cached: CachedRecord,
    *,
    reusable_signals: set[str],
    fresh_scores: dict[str, float],
    fresh_versions: dict[str, str],
    fresh_raw: dict[str, object],
) -> tuple[dict[str, float], dict[str, str], dict[str, object]]:
    """`reusable_signals` はキャッシュから、それ以外は `fresh_*` から取って合成。

    新しい結果 dict を返す (in-place ではない)。
    """
    scores: dict[str, float] = {}
    versions: dict[str, str] = {}
    raw: dict[str, object] = {}
    for code, version in fresh_versions.items():
        if code in reusable_signals and code in cached.signal_scores:
            scores[code] = cached.signal_scores[code]
            versions[code] = cached.signal_versions.get(code, version)
            if code in cached.signal_raw:
                raw[code] = cached.signal_raw[code]
        else:
            if code in fresh_scores:
                scores[code] = fresh_scores[code]
            versions[code] = version
            if code in fresh_raw:
                raw[code] = fresh_raw[code]
    return scores, versions, raw


def signal_result_from_cache(code: str, version: str, cached: CachedRecord):
    """キャッシュから 1 シグナル分の SignalResult を再構築する。

    hard_reject は cached.rejected_by に該当 code が含まれているかで判定。
    """
    from joryu.curate.signals import SignalResult

    score = cached.signal_scores.get(code, 0.0)
    raw = cached.signal_raw.get(code)
    hard = code in cached.rejected_by
    return SignalResult(code, version, score, raw, hard)


@dataclass
class CacheCounters:
    """差分実行サマリ用カウンタ (R-25 の前段)。"""

    cache_hits_full: int = 0
    cache_hits_partial: int = 0
    newly_evaluated: int = 0
    llm_calls_saved: int = 0
    rescore_only_misses: int = 0  # rescore-only モードでキャッシュ未ヒットの件数


__all__ = [
    "CacheCounters",
    "CacheIndex",
    "CacheReuse",
    "CachedRecord",
    "auto_detect_cache_paths",
    "load_cache_index",
    "merge_partial_signal_scores",
    "signal_result_from_cache",
]
