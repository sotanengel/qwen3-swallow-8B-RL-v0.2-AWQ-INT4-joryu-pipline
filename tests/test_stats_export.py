"""stats.py: write_stats_json の書き出し。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.stats import write_stats_json


def test_write_stats_json_writes_meta_and_counts(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M", "mode": "thinking"}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "stats.json"
    stats = write_stats_json(src, out)
    assert stats["total"] == 1
    assert stats["models"]["M"] == 1
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_meta"]["source_path"] == str(src)
    assert data["_meta"]["generated_at"]


def test_write_stats_json_handles_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "stats.json"
    stats = write_stats_json(tmp_path / "missing.jsonl", out)
    assert stats["total"] == 0
    assert out.exists()
