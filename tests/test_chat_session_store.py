"""ChatSessionStore SQLite 永続化のテスト (#221)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.chat.session import ChatSessionStore
from joryu.styles import StylePreset
from joryu.tool_executor import StubToolExecutor


@pytest.fixture
def styles() -> dict[str, StylePreset]:
    return {
        "prose": StylePreset(style_id="prose", label="散文", instruction="散文で。"),
        "qa_short": StylePreset(style_id="qa_short", label="短答", instruction="短く。"),
    }


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "chat" / "sessions.db"


def _create_kwargs(out_path: Path) -> dict:
    return {
        "base_system_prompt": "base prompt",
        "model_name": "test-model",
        "config_hash": "hash-1",
        "tools": [],
        "tool_ids": [],
        "out_path": out_path,
        "executor": StubToolExecutor(),
    }


def test_create_and_get_persists_across_store_instances(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store1 = ChatSessionStore(db_path=db_path)
    session = store1.create(styles, **_create_kwargs(out_path))
    session_id = session.session_id

    store2 = ChatSessionStore(db_path=db_path)
    loaded = store2.get(session_id)
    assert loaded is not None
    assert loaded.session_id == session_id
    assert set(loaded.columns.keys()) == {"prose", "qa_short"}
    assert all(col.turn_index == 0 for col in loaded.columns.values())


def test_save_persists_column_mutations(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    session = store.create(styles, **_create_kwargs(out_path))
    col = session.columns["prose"]
    col.messages.append({"role": "user", "content": "hello"})
    col.turn_index = 1
    store.save(session)

    reloaded = ChatSessionStore(db_path=db_path).get(session.session_id)
    assert reloaded is not None
    assert reloaded.columns["prose"].turn_index == 1
    assert reloaded.columns["prose"].messages == [{"role": "user", "content": "hello"}]


def test_delete_removes_session(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    session = store.create(styles, **_create_kwargs(out_path))
    assert store.delete(session.session_id) is True
    assert store.get(session.session_id) is None

    store2 = ChatSessionStore(db_path=db_path)
    assert store2.get(session.session_id) is None


def test_list_sessions_ordered_by_last_updated(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    s1 = store.create(styles, **_create_kwargs(out_path))
    s2 = store.create(styles, **_create_kwargs(out_path))
    s1.state.last_updated_at = 100.0
    store._db.upsert(s1)
    s2.state.last_updated_at = 200.0
    store._db.upsert(s2)

    items, next_cursor = store.list_sessions(limit=10)
    assert len(items) == 2
    assert items[0].session_id == s2.session_id
    assert items[1].session_id == s1.session_id
    assert next_cursor is None


def test_list_sessions_pagination(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    ids: list[str] = []
    for i in range(3):
        s = store.create(styles, **_create_kwargs(out_path))
        s.state.last_updated_at = float(300 - i)
        store._db.upsert(s)
        ids.append(s.session_id)

    page1, cursor = store.list_sessions(limit=2)
    assert len(page1) == 2
    assert cursor is not None

    page2, next_cursor = store.list_sessions(limit=2, cursor=cursor)
    assert len(page2) == 1
    assert next_cursor is None


def test_set_title_if_empty_only_once(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    session = store.create(styles, **_create_kwargs(out_path))
    long_prompt = "あ" * 50
    store.set_title_if_empty(session, long_prompt)
    assert session.title == "あ" * 30
    store.set_title_if_empty(session, "別のタイトル")
    assert session.title == "あ" * 30


def test_update_title(
    db_path: Path,
    styles: dict[str, StylePreset],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out.jsonl"
    store = ChatSessionStore(db_path=db_path)
    session = store.create(styles, **_create_kwargs(out_path))
    assert store.update_title(session.session_id, "手動タイトル") is True
    loaded = store.get(session.session_id)
    assert loaded is not None
    assert loaded.title == "手動タイトル"
