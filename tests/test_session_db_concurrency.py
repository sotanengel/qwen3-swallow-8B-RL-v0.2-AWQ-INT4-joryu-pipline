"""SessionDatabase 並行 upsert の concurrency テスト。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from joryu.chat.session import ChatSessionStore
from joryu.chat.session_db import SessionDatabase
from joryu.styles import StylePreset
from joryu.tool_executor import StubToolExecutor


def _styles() -> dict[str, StylePreset]:
    return {
        "prose": StylePreset(style_id="prose", label="散文", instruction="散文で。"),
    }


def test_concurrency_session_db_parallel_upserts(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    session = store.create(
        _styles(),
        base_system_prompt="base",
        model_name="test-model",
        config_hash="hash-1",
        tools=[],
        tool_ids=[],
        out_path=out_path,
        executor=StubToolExecutor(),
    )
    session_id = session.session_id
    db = SessionDatabase(db_path)
    errors: list[Exception] = []

    def _worker(turn: int) -> None:
        try:
            loaded = db.load(session_id)
            if loaded is None:
                raise RuntimeError("session missing")
            loaded.state.last_updated_at = time.time() + turn * 0.001
            loaded.columns["prose"].turn_index = turn
            db.upsert(loaded)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert not errors
    final = db.load(session_id)
    assert final is not None
    assert final.columns["prose"].turn_index in range(12)
