"""チャットビジネスロジック。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from joryu.chat.session import ChatSession, ChatSessionStore
from joryu.chat.sse import (
    monitor_client_disconnect,
    sse_all_columns,
    sse_single_column,
    with_heartbeat,
)
from joryu.chat.turn_persistence import TurnPersistence
from joryu.config import load_config
from joryu.datetime_context import format_date_context_ja, now_jst
from joryu.styles import StylePreset, load_styles
from joryu.system_prompt import build_system_prompt
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat, SupportsChatStream


class ChatService:
    """client / executor / config 組み立てと SSE ストリーム生成。"""

    def __init__(
        self,
        *,
        repo_root: Path,
        session_store: ChatSessionStore,
        chat_client: SupportsChat,
        executor: ToolExecutor,
        stream_client: SupportsChatStream | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._session_store = session_store
        self._chat_client = chat_client
        self._executor = executor
        self._stream_client = stream_client
        self._cfg = load_config(repo_root / "config.yaml")
        TurnPersistence.configure_dedup(
            max_per_key=self._cfg.distill.max_records_per_prompt_style,
        )

    def load_styles(self) -> dict[str, StylePreset]:
        styles_path = self._repo_root / self._cfg.distill.styles_file
        return load_styles(styles_path)

    def create_session(self, styles: dict[str, StylePreset]) -> ChatSession:
        from joryu.tools import load_tools, merge_tools

        tools_map = load_tools(self._repo_root / self._cfg.distill.tools_file)
        tool_ids = sorted(tools_map.keys())
        tool_defs_list = [t for t in tools_map.values()]
        tools_schema = merge_tools([t.to_openai_schema() for t in tool_defs_list], [])
        out_path = self._repo_root / self._cfg.distill.out_dir / self._cfg.distill.out_file
        date_context = format_date_context_ja(now_jst())
        base_core = f"{date_context}\n\n{self._cfg.distill.system_prompt.rstrip()}"
        base_prompt = build_system_prompt(base=base_core, factual_guard=True)
        tool_definitions = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "invocation_rule": t.invocation_rule,
            }
            for t in tool_defs_list
        ]
        return self._session_store.create(
            styles,
            base_system_prompt=base_prompt,
            model_name=self._cfg.model.name,
            config_hash=self._cfg.fingerprint(),
            tools=tools_schema,
            tool_ids=tool_ids,
            tool_definitions=tool_definitions,
            out_path=out_path,
        )

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._session_store.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self._session_store.delete(session_id)

    def save_session(self, session: ChatSession) -> None:
        self._session_store.save(session)

    def list_sessions(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ):
        return self._session_store.list_sessions(limit=limit, cursor=cursor)

    def update_session_title(self, session_id: str, title: str) -> bool:
        return self._session_store.update_title(session_id, title)

    def set_title_if_empty(self, session: ChatSession, prompt: str) -> None:
        self._session_store.set_title_if_empty(session, prompt)

    async def stream_all_columns(
        self,
        session: ChatSession,
        prompt: str,
        *,
        request: Any | None = None,
    ) -> AsyncIterator[str]:
        cancel_event = asyncio.Event()
        monitor_task: asyncio.Task[None] | None = None
        if request is not None:
            monitor_task = asyncio.create_task(
                monitor_client_disconnect(request, cancel_event),
            )
        try:
            if all(col.turn_index == 0 for col in session.columns.values()):
                self.set_title_if_empty(session, prompt)
            async for chunk in with_heartbeat(
                sse_all_columns(
                    session,
                    prompt,
                    client=self._chat_client,
                    executor=self._executor,
                    stream_client=self._stream_client,
                    cancel_event=cancel_event,
                ),
            ):
                if cancel_event.is_set():
                    break
                yield chunk
        finally:
            cancel_event.set()
            if monitor_task is not None:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            self.save_session(session)

    async def stream_single_column(
        self,
        session: ChatSession,
        style_id: str,
        prompt: str,
        *,
        request: Any | None = None,
    ) -> AsyncIterator[str]:
        cancel_event = asyncio.Event()
        monitor_task: asyncio.Task[None] | None = None
        if request is not None:
            monitor_task = asyncio.create_task(
                monitor_client_disconnect(request, cancel_event),
            )
        try:
            async for chunk in with_heartbeat(
                sse_single_column(
                    session,
                    style_id,
                    prompt,
                    client=self._chat_client,
                    executor=self._executor,
                    stream_client=self._stream_client,
                    cancel_event=cancel_event,
                ),
            ):
                if cancel_event.is_set():
                    break
                yield chunk
        finally:
            cancel_event.set()
            if monitor_task is not None:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            self.save_session(session)
