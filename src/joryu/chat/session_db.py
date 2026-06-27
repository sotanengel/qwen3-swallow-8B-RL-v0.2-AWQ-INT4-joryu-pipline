"""ChatSessionStore 用 SQLite 永続化。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from joryu.chat.session_models import (
    ChatColumn,
    ChatSession,
    ChatSessionConfig,
    ChatSessionState,
    SessionListItem,
)
from joryu.styles import StylePreset


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            created_at REAL NOT NULL,
            last_updated_at REAL NOT NULL,
            config_json TEXT NOT NULL,
            columns_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
        ON chat_sessions(last_updated_at DESC, session_id DESC)
        """
    )
    conn.commit()


def _style_preset_to_dict(preset: StylePreset) -> dict[str, str]:
    return {
        "style_id": preset.style_id,
        "label": preset.label,
        "instruction": preset.instruction,
    }


def _style_preset_from_dict(data: dict[str, Any]) -> StylePreset:
    return StylePreset(
        style_id=str(data["style_id"]),
        label=str(data["label"]),
        instruction=str(data["instruction"]),
    )


def _config_to_dict(config: ChatSessionConfig) -> dict[str, Any]:
    return {
        "base_system_prompt": config.base_system_prompt,
        "model_name": config.model_name,
        "config_hash": config.config_hash,
        "tools": list(config.tools),
        "tool_ids": list(config.tool_ids),
        "tool_definitions": list(config.tool_definitions),
        "out_path": str(config.out_path),
        "style_presets": {sid: _style_preset_to_dict(p) for sid, p in config.style_presets.items()},
    }


def _config_from_dict(data: dict[str, Any]) -> ChatSessionConfig:
    presets_raw = data.get("style_presets") or {}
    return ChatSessionConfig(
        base_system_prompt=str(data["base_system_prompt"]),
        model_name=str(data["model_name"]),
        config_hash=str(data["config_hash"]),
        tools=tuple(data.get("tools") or []),
        tool_ids=tuple(data.get("tool_ids") or []),
        tool_definitions=tuple(data.get("tool_definitions") or []),
        out_path=Path(str(data["out_path"])),
        style_presets={sid: _style_preset_from_dict(body) for sid, body in presets_raw.items()},
    )


def _columns_to_dict(columns: dict[str, ChatColumn]) -> dict[str, Any]:
    return {
        sid: {
            "style_id": col.style_id,
            "label": col.label,
            "messages": col.messages,
            "turn_index": col.turn_index,
        }
        for sid, col in columns.items()
    }


def _columns_from_dict(data: dict[str, Any]) -> dict[str, ChatColumn]:
    out: dict[str, ChatColumn] = {}
    for sid, body in data.items():
        out[sid] = ChatColumn(
            style_id=str(body["style_id"]),
            label=str(body["label"]),
            messages=list(body.get("messages") or []),
            turn_index=int(body.get("turn_index") or 0),
        )
    return out


def _session_to_row(session: ChatSession) -> tuple[Any, ...]:
    return (
        session.session_id,
        session.title,
        session.created_at,
        session.last_updated_at,
        json.dumps(_config_to_dict(session.config), ensure_ascii=False),
        json.dumps(_columns_to_dict(session.columns), ensure_ascii=False),
    )


def _row_to_session(row: sqlite3.Row) -> ChatSession:
    config = _config_from_dict(json.loads(row["config_json"]))
    columns = _columns_from_dict(json.loads(row["columns_json"]))
    state = ChatSessionState(
        session_id=row["session_id"],
        columns=columns,
        created_at=float(row["created_at"]),
        last_updated_at=float(row["last_updated_at"]),
        title=row["title"],
    )
    return ChatSession(config=config, state=state)


def _turn_count(columns: dict[str, ChatColumn]) -> int:
    if not columns:
        return 0
    return max(col.turn_index for col in columns.values())


class SessionDatabase:
    """SQLite バックエンド。"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            _ensure_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(self, session: ChatSession) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, title, created_at, last_updated_at,
                    config_json, columns_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    last_updated_at=excluded.last_updated_at,
                    config_json=excluded.config_json,
                    columns_json=excluded.columns_json
                """,
                _session_to_row(session),
            )
            conn.commit()

    def load(self, session_id: str) -> ChatSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_session(row)

    def delete(self, session_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def list_sessions(
        self,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[SessionListItem], str | None]:
        params: list[Any] = []
        where = ""
        if cursor:
            parts = cursor.split(":", 1)
            if len(parts) == 2:
                cursor_updated, cursor_id = parts
                where = "WHERE (last_updated_at < ? OR (last_updated_at = ? AND session_id < ?))"
                params.extend([float(cursor_updated), float(cursor_updated), cursor_id])

        query = f"""
            SELECT session_id, title, created_at, last_updated_at, columns_json
            FROM chat_sessions
            {where}
            ORDER BY last_updated_at DESC, session_id DESC
            LIMIT ?
        """
        params.append(limit + 1)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items: list[SessionListItem] = []
        for row in page_rows:
            columns = _columns_from_dict(json.loads(row["columns_json"]))
            items.append(
                SessionListItem(
                    session_id=row["session_id"],
                    title=row["title"],
                    created_at=float(row["created_at"]),
                    last_updated_at=float(row["last_updated_at"]),
                    turn_count=_turn_count(columns),
                )
            )

        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = f"{float(last['last_updated_at'])}:{last['session_id']}"
        return items, next_cursor
