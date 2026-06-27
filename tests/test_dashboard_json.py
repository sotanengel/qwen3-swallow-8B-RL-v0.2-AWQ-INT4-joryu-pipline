"""dashboard_json.py: 原子的 JSON 書き出しのユニットテスト。"""

from __future__ import annotations

import json
import platform
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from joryu.dashboard_json import write_dashboard_json


def test_write_dashboard_json_creates_file(tmp_path: Path) -> None:
    dst = tmp_path / "dashboard" / "public" / "stats.json"
    src = tmp_path / "data" / "distilled" / "responses.jsonl"
    src.parent.mkdir(parents=True)
    src.write_text("{}\n", encoding="utf-8")

    write_dashboard_json(dst, {"total": 3}, source_path=src)

    assert dst.is_file()
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert payload["total"] == 3
    assert payload["_meta"]["source_path"] == str(src)


def test_concurrent_writes_do_not_raise(tmp_path: Path) -> None:
    """蒸留中 stats 更新と runner 側 refresh が同時に走っても ENOENT にならない。"""
    dst = tmp_path / "dashboard" / "public" / "stats.json"
    src = tmp_path / "data" / "distilled" / "responses.jsonl"
    src.parent.mkdir(parents=True)
    src.write_text("{}\n", encoding="utf-8")

    def _write(n: int) -> None:
        write_dashboard_json(dst, {"total": n}, source_path=src)

    with ThreadPoolExecutor(max_workers=4 if platform.system() == "Windows" else 16) as pool:
        list(pool.map(_write, range(100)))

    assert dst.is_file()
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert "total" in payload
    assert "_meta" in payload
