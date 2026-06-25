"""stats.py: JSONL から dashboard 用統計を計算する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.stats import compute_stats, length_bins


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_basic_counts(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P1", "answer": "ans1", "model": "M", "mode": "thinking"},
            {"prompt": "P2", "answer": "ans22", "model": "M", "mode": "nothinking"},
            {"prompt": "P3", "answer": "ans333", "model": "M", "mode": "thinking"},
        ],
    )
    stats = compute_stats(p)
    assert stats["total"] == 3
    assert stats["models"] == {"M": 3}
    assert stats["modes"]["thinking"] == 2
    assert stats["modes"]["nothinking"] == 1


def test_category_and_style_histograms(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P", "category": "国語", "style_id": "formal", "answer": "a"},
            {"prompt": "P", "category": "国語", "style_id": "dialog", "answer": "a"},
            {"prompt": "P", "category": "数学", "style_id": "formal", "answer": "a"},
        ],
    )
    stats = compute_stats(p)
    assert stats["categories"] == {"国語": 2, "数学": 1}
    assert stats["styles"] == {"formal": 2, "dialog": 1}


def test_length_bins_buckets() -> None:
    bins = length_bins([5, 12, 99, 200, 1500])
    # 既定 bin 境界: 0,50,100,200,500,1000,2000,5000
    assert sum(v["count"] for v in bins) == 5
    # 5 -> 0..50, 12 -> 0..50, 99 -> 50..100, 200 -> 200..500, 1500 -> 1000..2000
    counts = {(b["lo"], b["hi"]): b["count"] for b in bins}
    assert counts[(0, 50)] == 2
    assert counts[(50, 100)] == 1
    assert counts[(200, 500)] == 1
    assert counts[(1000, 2000)] == 1


def test_answer_length_distribution(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P", "answer": "a" * 10},
            {"prompt": "P", "answer": "b" * 75},
            {"prompt": "P", "answer": "c" * 250},
        ],
    )
    stats = compute_stats(p)
    bins = stats["answer_length"]["bins"]
    counts = {(b["lo"], b["hi"]): b["count"] for b in bins}
    assert counts[(0, 50)] == 1
    assert counts[(50, 100)] == 1
    assert counts[(200, 500)] == 1
    assert stats["answer_length"]["mean"] > 0
    assert stats["answer_length"]["max"] == 250


def test_thinking_length_only_for_thinking_rows(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P", "answer": "a", "thinking_trace": "x" * 30, "mode": "thinking"},
            {"prompt": "P", "answer": "a", "thinking_trace": None, "mode": "nothinking"},
            {"prompt": "P", "answer": "a", "thinking_trace": "y" * 60, "mode": "thinking"},
        ],
    )
    stats = compute_stats(p)
    assert stats["thinking_length"]["count"] == 2
    assert stats["thinking_length"]["max"] == 60


def test_sampling_distribution(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P", "answer": "a", "sampling": {"temperature": 0.6, "top_p": 0.95}},
            {"prompt": "P", "answer": "a", "sampling": {"temperature": 0.6, "top_p": 0.95}},
            {"prompt": "P", "answer": "a", "sampling": {"temperature": 0.3, "top_p": 0.9}},
        ],
    )
    stats = compute_stats(p)
    assert stats["sampling"]["temperature"]["0.6"] == 2
    assert stats["sampling"]["temperature"]["0.3"] == 1
    assert stats["sampling"]["top_p"]["0.95"] == 2
    assert stats["sampling"]["top_p"]["0.9"] == 1


def test_time_histogram_by_day(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P", "answer": "a", "created_at": "2026-06-21T00:00:00+00:00"},
            {"prompt": "P", "answer": "a", "created_at": "2026-06-21T23:59:00+00:00"},
            {"prompt": "P", "answer": "a", "created_at": "2026-06-22T01:00:00+00:00"},
        ],
    )
    stats = compute_stats(p)
    assert stats["timeline_daily"]["2026-06-21"] == 2
    assert stats["timeline_daily"]["2026-06-22"] == 1


def test_truncated_rate(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {"prompt": "P1", "answer": "完結した回答です。"},
            {"prompt": "P2", "answer": "途中\n\n## 1. 見出し"},
            {"prompt": "P3", "answer": "a", "finish_reason": "length"},
        ],
    )
    stats = compute_stats(p)
    assert stats["truncated_count"] == 2
    assert stats["truncated_rate"] == pytest.approx(2 / 3)


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    stats = compute_stats(tmp_path / "nope.jsonl")
    assert stats["total"] == 0
    assert stats["models"] == {}


def test_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    p.write_text(
        '{"prompt":"P","answer":"a","model":"M"}\nnot json\n\n{"x":1}\n',
        encoding="utf-8",
    )
    stats = compute_stats(p)
    assert stats["total"] == 1  # only the valid one with a prompt


def test_tool_call_metrics(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {
                "prompt": "P1",
                "answer": "a",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [{"name": "search", "arguments": {"query": "x"}}],
            },
            {
                "prompt": "P2",
                "answer": "b",
                "tools": [{"type": "function", "function": {"name": "calc"}}],
                "tool_calls": [],
                "thinking_trace": "We should use search function to get data.",
            },
            {"prompt": "P3", "answer": "c"},
        ],
    )
    stats = compute_stats(p)
    assert stats["tool_records"] == 2
    assert stats["tool_call_records"] == 1
    assert stats["total_tool_calls"] == 1
    assert stats["tool_call_rate"] == pytest.approx(0.5)
    assert stats["tool_calls_per_record"] == pytest.approx(1 / 3)
    assert stats["tool_name_counts"] == {"search": 1}
    assert stats["tool_planned_not_called_count"] == 1
    assert stats["tool_planned_but_not_called_rate"] == pytest.approx(0.5)


def test_bare_json_and_suspected_metrics(tmp_path: Path) -> None:
    """#103: bare JSON 由来 tool_call と suspected_unparsed_tool_calls の集計。"""
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {
                # bare JSON 由来: raw に <tool_call> も ``` も含まない
                "prompt": "P1",
                "answer": "a",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [
                    {
                        "name": "search",
                        "arguments": {"query": "x"},
                        "raw": '{"name": "search", "arguments": {"query": "x"}}',
                    }
                ],
            },
            {
                # 旧形式 <tool_call> タグ由来: bare 扱いしない
                "prompt": "P2",
                "answer": "b",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [
                    {
                        "name": "search",
                        "arguments": {"query": "y"},
                        "raw": '<tool_call>{"name":"search","arguments":{"query":"y"}}</tool_call>',
                    }
                ],
            },
            {
                # tool_call 抽出失敗 → suspected hints だけ残る
                "prompt": "P3",
                "answer": "c",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [],
                "suspected_unparsed_tool_calls": ['前置き {"name": "rm_rf", "arguments": {}}'],
            },
            # 旧データ (新 key 無し) は無視され壊さない
            {"prompt": "P4", "answer": "d"},
        ],
    )
    stats = compute_stats(p)
    assert stats["bare_json_tool_call_records"] == 1
    assert stats["suspected_unparsed_tool_call_records"] == 1


def test_empty_stats_contains_new_keys() -> None:
    """空 JSONL でも新キーが含まれる (dashboard 後方互換)。"""
    from joryu.stats import _empty_stats

    s = _empty_stats()
    assert s["bare_json_tool_call_records"] == 0
    assert s["suspected_unparsed_tool_call_records"] == 0
    assert s["no_think_fallback_used_records"] == 0
    assert s["no_think_fallback_rescued_count"] == 0


def test_no_think_fallback_rescued_metrics(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    _write(
        p,
        [
            {
                "prompt": "P1",
                "answer": "a",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [{"name": "search", "arguments": {"query": "x"}}],
                "no_think_fallback_used": True,
                "tool_call_recovery": {
                    "no_think_fallback_succeeded": True,
                    "succeeded": True,
                },
            },
            {
                "prompt": "P2",
                "answer": "b",
                "tools": [{"type": "function", "function": {"name": "search"}}],
                "tool_calls": [],
                "no_think_fallback_used": True,
                "tool_call_recovery": {"no_think_fallback_succeeded": False},
            },
        ],
    )
    stats = compute_stats(p)
    assert stats["no_think_fallback_used_records"] == 2
    assert stats["no_think_fallback_rescued_count"] == 1
