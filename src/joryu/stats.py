"""蒸留 JSONL からダッシュボード用の統計量を計算する。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from joryu.dashboard_json import write_dashboard_json
from joryu.io.jsonl import iter_jsonl
from joryu.paths import STATS_JSON_REL, resolve_repo_root, resolve_stats_output_path
from joryu.tool_intent import thinking_plans_tool_use
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


def _record_has_tools(rec: dict[str, Any]) -> bool:
    tools = rec.get("tools")
    return isinstance(tools, list) and len(tools) > 0


def _record_tool_call_names(rec: dict[str, Any]) -> list[str]:
    tool_calls = rec.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    names: list[str] = []
    for call in tool_calls:
        if isinstance(call, dict) and isinstance(call.get("name"), str):
            names.append(call["name"])
    return names


def _record_has_bare_json_tool_call(rec: dict[str, Any]) -> bool:
    """tool_calls[*].raw が `<tool_call>` も ```` ``` ```` も含まない → bare JSON 由来。

    旧データの raw が空文字 ("" or 欠落) のケースは bare 扱いしない (旧 record 互換)。
    """
    tool_calls = rec.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        raw = call.get("raw")
        if not isinstance(raw, str) or not raw.strip():
            continue
        if "<tool_call" in raw or "```" in raw:
            continue
        return True
    return False


def _record_has_suspected_unparsed_tool_call(rec: dict[str, Any]) -> bool:
    hints = rec.get("suspected_unparsed_tool_calls")
    return isinstance(hints, list) and len(hints) > 0


def _thinking_plans_tool_use(rec: dict[str, Any]) -> bool:
    trace = rec.get("thinking_trace") or rec.get("reasoning") or ""
    if not isinstance(trace, str) or not trace.strip():
        return False
    return thinking_plans_tool_use(trace)


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
    tool_records = 0
    tool_call_records = 0
    total_tool_calls = 0
    tool_name_counts: Counter[str] = Counter()
    planned_not_called = 0
    bare_json_tool_call_records = 0
    suspected_unparsed_tool_call_records = 0
    no_think_fallback_used_records = 0
    no_think_fallback_rescued_count = 0

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

        has_tools = _record_has_tools(rec)
        if has_tools:
            tool_records += 1
        call_names = _record_tool_call_names(rec)
        if call_names:
            tool_call_records += 1
            total_tool_calls += len(call_names)
            for name in call_names:
                tool_name_counts[name] += 1
            if _record_has_bare_json_tool_call(rec):
                bare_json_tool_call_records += 1
        elif has_tools and _thinking_plans_tool_use(rec):
            planned_not_called += 1

        if _record_has_suspected_unparsed_tool_call(rec):
            suspected_unparsed_tool_call_records += 1

        if rec.get("no_think_fallback_used"):
            no_think_fallback_used_records += 1
            recovery = rec.get("tool_call_recovery")
            if isinstance(recovery, dict) and recovery.get("no_think_fallback_succeeded"):
                no_think_fallback_rescued_count += 1
            elif call_names:
                no_think_fallback_rescued_count += 1

    truncated_rate = (truncated_count / total) if total else 0.0
    tool_call_rate = (tool_call_records / tool_records) if tool_records else 0.0
    tool_calls_per_record = (total_tool_calls / total) if total else 0.0
    tool_planned_but_not_called_rate = (planned_not_called / tool_records) if tool_records else 0.0
    return {
        "total": total,
        "truncated_count": truncated_count,
        "truncated_rate": truncated_rate,
        "tool_records": tool_records,
        "tool_call_records": tool_call_records,
        "total_tool_calls": total_tool_calls,
        "tool_call_rate": tool_call_rate,
        "tool_calls_per_record": tool_calls_per_record,
        "tool_name_counts": dict(tool_name_counts),
        "tool_planned_not_called_count": planned_not_called,
        "tool_planned_but_not_called_rate": tool_planned_but_not_called_rate,
        "bare_json_tool_call_records": bare_json_tool_call_records,
        "suspected_unparsed_tool_call_records": suspected_unparsed_tool_call_records,
        "no_think_fallback_used_records": no_think_fallback_used_records,
        "no_think_fallback_rescued_count": no_think_fallback_rescued_count,
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
        "tool_records": 0,
        "tool_call_records": 0,
        "total_tool_calls": 0,
        "tool_call_rate": 0.0,
        "tool_calls_per_record": 0.0,
        "tool_name_counts": {},
        "tool_planned_not_called_count": 0,
        "tool_planned_but_not_called_rate": 0.0,
        "bare_json_tool_call_records": 0,
        "suspected_unparsed_tool_call_records": 0,
        "no_think_fallback_used_records": 0,
        "no_think_fallback_rescued_count": 0,
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
