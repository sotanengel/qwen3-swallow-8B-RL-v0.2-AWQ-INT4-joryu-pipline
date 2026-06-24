"""search/record_key.py のテスト (dashboard recordId と一致)。"""

from __future__ import annotations

from joryu.search.record_key import record_id, record_key


def test_record_key_joins_fields() -> None:
    rec = {
        "prompt": "P",
        "category": "国語",
        "mode": "thinking",
        "style_id": "s1",
        "created_at": "2026-01-01T00:00:00Z",
        "config_hash": "abc",
    }
    key = record_key(rec)
    assert "\x1e" in key
    assert key.startswith("P")


def test_record_id_stable() -> None:
    rec = {
        "prompt": "桜の特徴",
        "category": "国語",
        "mode": "thinking",
        "style_id": "default",
        "created_at": "2026-01-01T00:00:00Z",
        "config_hash": "abc123",
    }
    assert record_id(rec) == record_id(rec)


def test_record_id_differs_for_different_records() -> None:
    a = {"prompt": "A", "answer": "1"}
    b = {"prompt": "B", "answer": "2"}
    assert record_id(a) != record_id(b)
