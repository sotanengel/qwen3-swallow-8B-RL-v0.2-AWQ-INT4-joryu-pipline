"""curate ダッシュボード用統計 (R-18 バックエンド)。

`scores.jsonl` を 1 pass 走査し、ダッシュボード描画に十分な集約を出す。
出力先 = `dashboard/public/curation.json`。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.curate.judge_client import RUBRIC_KEYS
from joryu.stats import length_bins

DEFAULT_CURATION_OUTPUT = "dashboard/public/curation.json"

_SCORE_BIN_EDGES: tuple[int, ...] = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90)


def _score_bins(values: list[float]) -> list[dict[str, Any]]:
    """`final_score` を 0–100% に変換したヒストグラム。"""
    scaled = [int(round(v * 100)) for v in values]
    return length_bins(scaled, _SCORE_BIN_EDGES)


def compute_curation_stats(scores_jsonl: str | Path) -> dict[str, Any]:
    """`scores.jsonl` を読んで集約を返す。"""
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
        if isinstance(score, int | float):
            final_scores.append(float(score))
        if row.get("accepted"):
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
        sid = row.get("style_id")
        if isinstance(sid, str) and sid:
            style_total[sid] += 1
            if row.get("accepted"):
                style_kept[sid] += 1

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
    }


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
    }


def write_curation_json(
    scores_jsonl: str | Path,
    dst: str | Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """`dashboard/public/curation.json` を書き出す。"""
    src_path = Path(scores_jsonl)
    dst_path = Path(dst)
    stats = compute_curation_stats(src_path)
    stats["_meta"] = {
        "source_path": str(src_path),
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
    }
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats
