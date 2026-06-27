"""チャットセッションのデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from joryu.styles import StylePreset

TITLE_MAX_LEN = 30


@dataclass
class ChatColumn:
    style_id: str
    label: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    turn_index: int = 0


@dataclass(frozen=True)
class ChatSessionConfig:
    base_system_prompt: str = ""
    model_name: str = ""
    config_hash: str = ""
    tools: tuple[dict[str, Any], ...] = ()
    tool_ids: tuple[str, ...] = ()
    out_path: Path = field(default_factory=lambda: Path("data/distilled/responses.jsonl"))
    style_presets: dict[str, StylePreset] = field(default_factory=dict)


@dataclass
class ChatSessionState:
    session_id: str
    columns: dict[str, ChatColumn]
    created_at: float
    last_updated_at: float
    title: str | None = None


@dataclass
class ChatSession:
    config: ChatSessionConfig
    state: ChatSessionState

    @property
    def session_id(self) -> str:
        return self.state.session_id

    @property
    def columns(self) -> dict[str, ChatColumn]:
        return self.state.columns

    @property
    def created_at(self) -> float:
        return self.state.created_at

    @property
    def last_updated_at(self) -> float:
        return self.state.last_updated_at

    @property
    def title(self) -> str | None:
        return self.state.title

    @property
    def base_system_prompt(self) -> str:
        return self.config.base_system_prompt

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def config_hash(self) -> str:
        return self.config.config_hash

    @property
    def tools(self) -> list[dict[str, Any]]:
        return list(self.config.tools)

    @property
    def tool_ids(self) -> list[str]:
        return list(self.config.tool_ids)

    @property
    def out_path(self) -> Path:
        return self.config.out_path

    @property
    def style_presets(self) -> dict[str, StylePreset]:
        return self.config.style_presets


@dataclass(frozen=True)
class SessionListItem:
    session_id: str
    title: str | None
    created_at: float
    last_updated_at: float
    turn_count: int
