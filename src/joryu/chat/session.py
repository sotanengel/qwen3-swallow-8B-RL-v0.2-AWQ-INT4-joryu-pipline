"""チャットセッション管理（SQLite 永続化）。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from joryu.chat.session_db import SessionDatabase
from joryu.chat.session_models import (
    TITLE_MAX_LEN,
    ChatColumn,
    ChatSession,
    ChatSessionConfig,
    ChatSessionState,
    SessionListItem,
)
from joryu.styles import StylePreset
from joryu.tool_executor import ToolExecutor

__all__ = [
    "TITLE_MAX_LEN",
    "ChatColumn",
    "ChatSession",
    "ChatSessionConfig",
    "ChatSessionState",
    "ChatSessionStore",
    "SessionListItem",
]


class ChatSessionStore:
    """SQLite 永続化セッションストア。"""

    def __init__(self, *, db_path: Path) -> None:
        self._db = SessionDatabase(db_path)

    def create(
        self,
        styles: dict[str, StylePreset],
        *,
        base_system_prompt: str,
        model_name: str,
        config_hash: str,
        tools: list[dict[str, Any]],
        tool_ids: list[str],
        out_path: Path,
        executor: ToolExecutor | None = None,
    ) -> ChatSession:
        del executor  # executor は session に保持しない (DI 経由で渡す)
        now = time.time()
        session_id = str(uuid.uuid4())
        columns = {
            sid: ChatColumn(style_id=preset.style_id, label=preset.label)
            for sid, preset in sorted(styles.items())
        }
        config = ChatSessionConfig(
            base_system_prompt=base_system_prompt,
            model_name=model_name,
            config_hash=config_hash,
            tools=tuple(tools),
            tool_ids=tuple(tool_ids),
            out_path=out_path,
            style_presets=dict(styles),
        )
        state = ChatSessionState(
            session_id=session_id,
            columns=columns,
            created_at=now,
            last_updated_at=now,
        )
        session = ChatSession(config=config, state=state)
        self._db.upsert(session)
        return session

    def get(self, session_id: str) -> ChatSession | None:
        return self._db.load(session_id)

    def save(self, session: ChatSession) -> None:
        session.state.last_updated_at = time.time()
        self._db.upsert(session)

    def delete(self, session_id: str) -> bool:
        return self._db.delete(session_id)

    def list_sessions(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[SessionListItem], str | None]:
        return self._db.list_sessions(limit=limit, cursor=cursor)

    def set_title_if_empty(self, session: ChatSession, prompt: str) -> None:
        if session.title is not None:
            return
        text = prompt.strip()
        if not text:
            return
        session.state.title = text[:TITLE_MAX_LEN]
        self.save(session)

    def update_title(self, session_id: str, title: str) -> bool:
        session = self.get(session_id)
        if session is None:
            return False
        session.state.title = title.strip() or None
        self.save(session)
        return True
