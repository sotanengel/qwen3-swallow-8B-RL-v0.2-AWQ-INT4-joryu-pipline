"""蒸留 JSONL からダッシュボード用の統計量を計算する。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from joryu.dashboard_json import write_dashboard_json
from joryu.io.jsonl import iter_jsonl
from joryu.paths import STATS_JSON_REL, resolve_repo_root, resolve_stats_output_path
from joryu.truncation import record_looks_truncated

DEFAULT_STATS_OUTPUT = STATS_JSON_REL

__all__ = [
    "DEFAULT_STATS_OUTPUT",
    "compute_stats",
    "length_bins",
    "resolve_repo_root",
    "resolve_stats_output_path",
    "write_stats_json",
]

# 文字数ベースのビン (token 換算はモデル依存なので char で近似する)。
_LENGTH_BIN_EDGES: tuple[int, ...] = (0, 50, 100, 200, 500, 1000, 2000, 5000)


def length_bins(values: list[int], edges: tuple[int, ...] = _LENGTH_BIN_EDGES) -> list[dict]:
    """値リストを [lo, hi) で集計したヒストグラムを返す。最後のビンは [edges[-1], +inf)。"""
    out: list[dict] = []
    bounds = list(edges) + [float("inf")]
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        c = sum(1 for v in values if lo <= v < hi)
        out.append({"lo": int(lo), "hi": (int(hi) if hi != float("inf") else None), "count": c})
    return out


def _summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": 0.0, "max": 0, "min": 0, "bins": length_bins([])}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "max": max(values),
        "min": min(values),
        "bins": length_bins(values),
    }


def _ts_day(text: str) -> str | None:
    if not isinstance(text, str) or len(text) < 10:
        return None
    return text[:10]


def _round_str(value: Any) -> str | None:
    if isinstance(value, bool):  # bool は int の subclass なので除外
        return None
    if isinstance(value, int | float):
        return f"{round(float(value), 4)!s}"
    return None


def compute_stats(jsonl_path: str | Path) -> dict[str, Any]:
    """JSONL を 1 パスで走査し、ダッシュボード描画に十分な統計を返す。"""
    p = Path(jsonl_path)
    if not p.exists():
        return _empty_stats()

    total = 0
    models: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    styles: Counter[str] = Counter()
    answer_lens: list[int] = []
    thinking_lens: list[int] = []
    sampling_temps: Counter[str] = Counter()
    sampling_top_ps: Counter[str] = Counter()
    timeline_daily: Counter[str] = Counter()
    truncated_count = 0

    for rec in iter_jsonl(p):
        prompt = rec.get("prompt")
        if not (isinstance(prompt, str) and prompt):
            continue
        total += 1

        if (m := rec.get("model")) and isinstance(m, str):
            models[m] += 1
        if (mode := rec.get("mode")) and isinstance(mode, str):
            modes[mode] += 1
        if (cat := rec.get("category")) and isinstance(cat, str):
            categories[cat] += 1
        if (sid := rec.get("style_id")) and isinstance(sid, str):
            styles[sid] += 1

        ans = rec.get("answer")
        if isinstance(ans, str):
            answer_lens.append(len(ans))

        tt = rec.get("thinking_trace")
        if isinstance(tt, str) and tt:
            thinking_lens.append(len(tt))

        sampling = rec.get("sampling")
        if isinstance(sampling, dict):
            if (t := _round_str(sampling.get("temperature"))) is not None:
                sampling_temps[t] += 1
            if (tp := _round_str(sampling.get("top_p"))) is not None:
                sampling_top_ps[tp] += 1

        if (day := _ts_day(rec.get("created_at"))) is not None:
            timeline_daily[day] += 1

        if record_looks_truncated(rec):
            truncated_count += 1

    truncated_rate = (truncated_count / total) if total else 0.0
    return {
        "total": total,
        "truncated_count": truncated_count,
        "truncated_rate": truncated_rate,
        "models": dict(models),
        "modes": dict(modes),
        "categories": dict(categories),
        "styles": dict(styles),
        "answer_length": _summary(answer_lens),
        "thinking_length": _summary(thinking_lens),
        "sampling": {
            "temperature": dict(sampling_temps),
            "top_p": dict(sampling_top_ps),
        },
        "timeline_daily": dict(timeline_daily),
    }


def _empty_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "models": {},
        "modes": {},
        "categories": {},
        "styles": {},
        "answer_length": _summary([]),
        "thinking_length": _summary([]),
        "sampling": {"temperature": {}, "top_p": {}},
        "timeline_daily": {},
        "truncated_count": 0,
        "truncated_rate": 0.0,
    }


def write_stats_json(
    src: str | Path,
    dst: str | Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """JSONL から統計を計算し dashboard 用 JSON を書き出す。"""
    src_path = Path(src)
    dst_path = Path(dst)
    stats = compute_stats(src_path)
    return write_dashboard_json(
        dst_path,
        stats,
        source_path=src_path,
        generated_at=generated_at,
    )
