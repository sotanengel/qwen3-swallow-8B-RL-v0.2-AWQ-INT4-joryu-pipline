"""curate ダッシュボード用統計 (R-18 バックエンド)。

`scores.jsonl` を 1 pass 走査し、ダッシュボード描画に十分な集約を出す。
出力先 = `dashboard/public/curation.json`。
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from joryu.curate.judge_client import RUBRIC_KEYS
from joryu.dashboard_json import write_dashboard_json
from joryu.paths import CURATION_JSON_REL
from joryu.stats import length_bins

DEFAULT_CURATION_OUTPUT = CURATION_JSON_REL
DEFAULT_REJECTED_SAMPLE_N = 20

_SCORE_BIN_EDGES: tuple[int, ...] = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90)


def _score_bins(values: list[float]) -> list[dict[str, Any]]:
    """`final_score` を 0–100% に変換したヒストグラム。"""
    scaled = [int(round(v * 100)) for v in values]
    return length_bins(scaled, _SCORE_BIN_EDGES)


def _sampling_key(sampling: Any) -> str | None:
    """`(temperature, top_p)` を `"t=0.6,p=0.95"` 形式の文字列にキー化。"""
    if not isinstance(sampling, dict):
        return None
    t = sampling.get("temperature")
    p = sampling.get("top_p")
    if not isinstance(t, int | float) or not isinstance(p, int | float):
        return None
    return f"t={float(t):g},p={float(p):g}"


def compute_curation_stats(
    scores_jsonl: str | Path,
    *,
    rejected_sample_n: int = DEFAULT_REJECTED_SAMPLE_N,
    rejected_sample_seed: int = 42,
) -> dict[str, Any]:
    """`scores.jsonl` を読んで集約を返す。

    rejected_sample_n: 棄却サンプルとして抽出する件数 (固定 seed で決定的)。
    """
    p = Path(scores_jsonl)
    if not p.exists():
        return _empty_stats()

    total = 0
    accepted = 0
    final_scores: list[float] = []
    rejected_reasons: Counter[str] = Counter()
    rubric_sums: dict[str, float] = dict.fromkeys(RUBRIC_KEYS, 0.0)
    rubric_count = 0
    style_kept: Counter[str] = Counter()
    style_total: Counter[str] = Counter()

    # sampling 別 / sampling × style クロス / mode 別
    sampling_total: Counter[str] = Counter()
    sampling_kept: Counter[str] = Counter()
    sampling_style_total: dict[tuple[str, str], int] = defaultdict(int)
    sampling_style_kept: dict[tuple[str, str], int] = defaultdict(int)
    mode_scores: dict[str, list[float]] = defaultdict(list)
    mode_kept: Counter[str] = Counter()
    mode_total: Counter[str] = Counter()

    # 棄却サンプル候補 (reservoir sampling だと過剰なので、まず全件溜めて最後に抽出)
    rejected_pool: list[dict[str, Any]] = []

    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        total += 1
        score = row.get("final_score")
        score_f: float | None = float(score) if isinstance(score, int | float) else None
        if score_f is not None:
            final_scores.append(score_f)
        is_accepted = bool(row.get("accepted"))
        if is_accepted:
            accepted += 1
        for reason in row.get("rejected_by") or []:
            if isinstance(reason, str):
                rejected_reasons[reason] += 1

        raw_dict = row.get("signal_raw") or {}
        if isinstance(raw_dict, dict):
            rubric_raw = raw_dict.get("LLM-RUBRIC")
            if isinstance(rubric_raw, dict):
                rubric_count += 1
                for k in RUBRIC_KEYS:
                    v = rubric_raw.get(k)
                    if isinstance(v, int | float):
                        rubric_sums[k] += float(v)

        sid = row.get("style_id") if isinstance(row.get("style_id"), str) else None
        mode = row.get("mode") if isinstance(row.get("mode"), str) else None
        samp_key = _sampling_key(row.get("sampling"))

        if sid:
            style_total[sid] += 1
            if is_accepted:
                style_kept[sid] += 1

        if samp_key:
            sampling_total[samp_key] += 1
            if is_accepted:
                sampling_kept[samp_key] += 1

        if samp_key and sid:
            sampling_style_total[(samp_key, sid)] += 1
            if is_accepted:
                sampling_style_kept[(samp_key, sid)] += 1

        if mode:
            mode_total[mode] += 1
            if is_accepted:
                mode_kept[mode] += 1
            if score_f is not None:
                mode_scores[mode].append(score_f)

        if not is_accepted:
            rejected_pool.append(
                {
                    "record_hash": row.get("record_hash"),
                    "prompt": _truncate(row.get("prompt"), 200),
                    "style_id": sid,
                    "mode": mode,
                    "rejected_by": row.get("rejected_by") or [],
                    "final_score": score_f,
                }
            )

    # 棄却サンプルの決定的抽出
    rng = random.Random(rejected_sample_seed)
    rejected_samples: list[dict[str, Any]] = []
    if rejected_pool:
        rng.shuffle(rejected_pool)
        rejected_samples = rejected_pool[:rejected_sample_n]

    return {
        "total": total,
        "accepted": accepted,
        "rejected": total - accepted,
        "keep_rate": (accepted / total) if total else 0.0,
        "score_bins": _score_bins(final_scores),
        "rejected_reasons_top": rejected_reasons.most_common(10),
        "rubric_avg": (
            {k: rubric_sums[k] / rubric_count for k in RUBRIC_KEYS} if rubric_count else {}
        ),
        "rubric_count": rubric_count,
        "by_style": {
            sid: {
                "total": style_total[sid],
                "kept": style_kept[sid],
                "keep_rate": (style_kept[sid] / style_total[sid]) if style_total[sid] else 0.0,
            }
            for sid in sorted(style_total)
        },
        "by_sampling": {
            samp: {
                "total": sampling_total[samp],
                "kept": sampling_kept[samp],
                "keep_rate": (sampling_kept[samp] / sampling_total[samp])
                if sampling_total[samp]
                else 0.0,
            }
            for samp in sorted(sampling_total)
        },
        "by_sampling_style": _serialize_cross(sampling_style_total, sampling_style_kept),
        "by_mode": {
            mode: {
                "total": mode_total[mode],
                "kept": mode_kept[mode],
                "keep_rate": (mode_kept[mode] / mode_total[mode]) if mode_total[mode] else 0.0,
                "score_bins": _score_bins(mode_scores[mode]),
            }
            for mode in sorted(mode_total)
        },
        "rejected_samples": rejected_samples,
    }


def _serialize_cross(
    total_map: dict[tuple[str, str], int],
    kept_map: dict[tuple[str, str], int],
) -> list[dict[str, Any]]:
    """sampling × style クロス集計を列リストに変換 (ヒートマップ描画用)。"""
    out: list[dict[str, Any]] = []
    for (samp, sid), n in sorted(total_map.items()):
        kept = kept_map.get((samp, sid), 0)
        out.append(
            {
                "sampling": samp,
                "style_id": sid,
                "total": n,
                "kept": kept,
                "keep_rate": (kept / n) if n else 0.0,
            }
        )
    return out


def _truncate(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len] + ("…" if len(value) > max_len else "")


def _empty_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "keep_rate": 0.0,
        "score_bins": _score_bins([]),
        "rejected_reasons_top": [],
        "rubric_avg": {},
        "rubric_count": 0,
        "by_style": {},
        "by_sampling": {},
        "by_sampling_style": [],
        "by_mode": {},
        "rejected_samples": [],
    }


def write_curation_json(
    scores_jsonl: str | Path,
    dst: str | Path,
    *,
    generated_at: datetime | None = None,
    rejected_sample_n: int = DEFAULT_REJECTED_SAMPLE_N,
) -> dict[str, Any]:
    """`dashboard/public/curation.json` を書き出す。"""
    src_path = Path(scores_jsonl)
    dst_path = Path(dst)
    stats = compute_curation_stats(src_path, rejected_sample_n=rejected_sample_n)
    return write_dashboard_json(
        dst_path,
        stats,
        source_path=src_path,
        generated_at=generated_at,
    )
