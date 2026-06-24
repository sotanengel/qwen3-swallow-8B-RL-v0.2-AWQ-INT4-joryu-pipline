"""search/index.py: BM25 インデックスのテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.search.index import SearchIndex, build_search_text


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    records = [
        {
            "prompt": "桜の特徴を教えて",
            "answer": "桜は春に咲く美しい花です",
            "mode": "thinking",
            "category": "国語",
            "style_id": "default",
            "model": "qwen3",
            "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "prompt": "1+1は",
            "answer": "2です",
            "mode": "nothinking",
            "category": "数学",
            "created_at": "2026-01-02T00:00:00Z",
        },
        {
            "prompt": "雪の結晶",
            "answer": "六角形の結晶構造を持つ",
            "mode": "thinking",
            "category": "理科",
            "thinking_trace": "雪について考える",
            "created_at": "2026-01-03T00:00:00Z",
        },
    ]
    p = tmp_path / "responses.jsonl"
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    p.write_text(lines, encoding="utf-8")
    return p


def test_build_search_text_concatenates_fields() -> None:
    rec = {
        "prompt": "P",
        "answer": "A",
        "thinking_trace": "T",
        "category": "C",
        "style_id": "S",
        "model": "M",
    }
    text = build_search_text(rec)
    assert "P" in text
    assert "A" in text
    assert "T" in text


def test_search_index_ranks_relevant_higher(sample_jsonl: Path, tmp_path: Path) -> None:
    index_dir = tmp_path / ".search_index"
    idx = SearchIndex(index_dir)
    idx.build(sample_jsonl)

    hits = idx.search("桜 春", mode="all", category=None, limit=10, offset=0)
    assert hits.total >= 1
    assert hits.hits[0].record["prompt"] == "桜の特徴を教えて"


def test_search_index_filters_by_mode(sample_jsonl: Path, tmp_path: Path) -> None:
    index_dir = tmp_path / ".search_index"
    idx = SearchIndex(index_dir)
    idx.build(sample_jsonl)

    hits = idx.search("1", mode="nothinking", category=None, limit=10, offset=0)
    assert all(h.record.get("mode") == "nothinking" for h in hits.hits)


def test_search_index_filters_by_category(sample_jsonl: Path, tmp_path: Path) -> None:
    index_dir = tmp_path / ".search_index"
    idx = SearchIndex(index_dir)
    idx.build(sample_jsonl)

    hits = idx.search("結晶", mode="all", category="理科", limit=10, offset=0)
    assert len(hits.hits) == 1
    assert hits.hits[0].record["category"] == "理科"


def test_search_index_rebuilds_when_stale(sample_jsonl: Path, tmp_path: Path) -> None:
    index_dir = tmp_path / ".search_index"
    idx = SearchIndex(index_dir)
    idx.build(sample_jsonl)
    assert idx.status().record_count == 3

    sample_jsonl.write_text(
        sample_jsonl.read_text(encoding="utf-8")
        + json.dumps({"prompt": "新規", "answer": "追加"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    idx.ensure_fresh(sample_jsonl)
    assert idx.status().record_count == 4


def test_search_index_empty_jsonl(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    idx = SearchIndex(tmp_path / ".search_index")
    idx.build(empty)
    assert idx.status().index_status == "empty"
