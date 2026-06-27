"""atomic_io / 並行書き込みのテスト。"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from joryu.atomic_io import atomic_write_text
from joryu.chat.session_db import SessionDatabase
from joryu.vllm_limits import VllmLimits, write_probe_limits


def test_write_probe_limits_concurrent_writes(tmp_path: Path) -> None:
    path = tmp_path / "vllm_limits.json"
    limits = VllmLimits(num_ctx=2048, num_predict=512)
    errors: list[Exception] = []

    def _writer(ctx: int) -> None:
        try:
            write_probe_limits(path, VllmLimits(num_ctx=ctx, num_predict=512))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(n,)) for n in range(2048, 2053)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not errors
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["num_ctx"] in {2048, 2049, 2050, 2051, 2052}
    assert payload["num_predict"] == limits.num_predict


def test_session_database_uses_wal_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    SessionDatabase(db_path)
    with sqlite3.connect(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_atomic_write_text_is_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    atomic_write_text(path, '{"ok": true}\n')
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
