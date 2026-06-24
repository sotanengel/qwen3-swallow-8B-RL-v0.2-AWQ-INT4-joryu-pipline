"""responses_store: record_id parity と JSONL 削除のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.responses_store import (
    delete_all_records,
    delete_record,
    load_records,
    record_id,
    write_records,
)

# dashboard/src/lib/jsonl.test.ts と同一フィクスチャ (TS recordId と parity 確認用)
THINKING_RECORD = {
    "prompt": "桜の特徴",
    "answer": "美しい花です",
    "mode": "thinking",
    "category": "国語",
    "style_id": "default",
    "created_at": "2026-01-01T00:00:00Z",
    "config_hash": "abc123",
    "thinking_trace": "桜について考える…",
    "model": "qwen3",
}

NOTHINKING_RECORD = {
    "prompt": "1+1",
    "answer": "2",
    "mode": "nothinking",
    "category": "数学",
    "created_at": "2026-01-02T00:00:00Z",
}

# TS jsonl.test.ts と同一フィクスチャで recordId() を実行した値
TS_THINKING_ID = "6g2dj4"
TS_NOTHINKING_ID = "1turkvu"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_record_id_matches_typescript() -> None:
    assert record_id(THINKING_RECORD) == TS_THINKING_ID
    assert record_id(NOTHINKING_RECORD) == TS_NOTHINKING_ID


def test_load_records_skips_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    path.write_text(
        '{"prompt":"ok","answer":"a"}\nnot-json\n\n{"prompt":"ok2","answer":"b"}\n',
        encoding="utf-8",
    )
    rows = load_records(path)
    assert len(rows) == 2
    assert rows[0]["prompt"] == "ok"
    assert rows[1]["prompt"] == "ok2"


def test_delete_record_removes_one(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    _write_jsonl(path, [THINKING_RECORD, NOTHINKING_RECORD])
    rid = record_id(THINKING_RECORD)
    remaining = delete_record(path, rid)
    assert remaining == 1
    rows = load_records(path)
    assert len(rows) == 1
    assert rows[0]["prompt"] == "1+1"


def test_delete_record_raises_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    _write_jsonl(path, [NOTHINKING_RECORD])
    with pytest.raises(KeyError):
        delete_record(path, "nonexistent")


def test_delete_all_records_clears_file(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    _write_jsonl(path, [THINKING_RECORD, NOTHINKING_RECORD])
    deleted = delete_all_records(path)
    assert deleted == 2
    assert load_records(path) == []


def test_write_records_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    write_records(path, [THINKING_RECORD])
    rows = load_records(path)
    assert len(rows) == 1
    assert rows[0]["prompt"] == "桜の特徴"
