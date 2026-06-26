"""インメモリチャットセッション管理。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from joryu.styles import StylePreset


@dataclass
class ChatColumn:
    style_id: str
    label: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    turn_index: int = 0


@dataclass
class ChatSession:
    session_id: str
    columns: dict[str, ChatColumn]
    created_at: float
    expires_at: float


class ChatSessionStore:
    """TTL 付きインメモリセッションストア。"""

    TTL_SECONDS = 1800  # 30 分

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def create(self, styles: dict[str, StylePreset]) -> ChatSession:
        self.purge_expired()
        now = time.monotonic()
        session_id = str(uuid.uuid4())
        columns = {
            sid: ChatColumn(style_id=preset.style_id, label=preset.label)
            for sid, preset in sorted(styles.items())
        }
        session = ChatSession(
            session_id=session_id,
            columns=columns,
            created_at=now,
            expires_at=now + self.TTL_SECONDS,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ChatSession | None:
        self.purge_expired()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if time.monotonic() > session.expires_at:
            del self._sessions[session_id]
            return None
        return session

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def purge_expired(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, s in self._sessions.items() if now > s.expires_at]
        for sid in expired:
            del self._sessions[sid]
