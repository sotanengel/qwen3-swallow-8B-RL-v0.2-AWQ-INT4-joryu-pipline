"""チャットビジネスロジック。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from joryu.chat.session import ChatSession, ChatSessionStore
from joryu.chat.sse import sse_all_columns, sse_single_column
from joryu.config import load_config
from joryu.styles import StylePreset, load_styles
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat


class ChatService:
    """client / executor / config 組み立てと SSE ストリーム生成。"""

    def __init__(
        self,
        *,
        repo_root: Path,
        session_store: ChatSessionStore,
        chat_client: SupportsChat,
        executor: ToolExecutor,
    ) -> None:
        self._repo_root = repo_root
        self._session_store = session_store
        self._chat_client = chat_client
        self._executor = executor
        self._cfg = load_config(repo_root / "config.yaml")

    def load_styles(self) -> dict[str, StylePreset]:
        styles_path = self._repo_root / self._cfg.distill.styles_file
        return load_styles(styles_path)

    def create_session(self, styles: dict[str, StylePreset]) -> ChatSession:
        from joryu.tools import load_tools, merge_tools

        tools_map = load_tools(self._repo_root / self._cfg.distill.tools_file)
        tool_ids = sorted(tools_map.keys())
        tools_schema = merge_tools([t.to_openai_schema() for t in tools_map.values()], [])
        out_path = self._repo_root / self._cfg.distill.out_dir / self._cfg.distill.out_file
        return self._session_store.create(
            styles,
            base_system_prompt=self._cfg.distill.system_prompt,
            model_name=self._cfg.model.name,
            config_hash=self._cfg.fingerprint(),
            tools=tools_schema,
            tool_ids=tool_ids,
            out_path=out_path,
        )

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._session_store.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self._session_store.delete(session_id)

    async def stream_all_columns(
        self,
        session: ChatSession,
        prompt: str,
    ) -> AsyncIterator[str]:
        async for chunk in sse_all_columns(
            session,
            prompt,
            client=self._chat_client,
            executor=self._executor,
        ):
            yield chunk

    async def stream_single_column(
        self,
        session: ChatSession,
        style_id: str,
        prompt: str,
    ) -> AsyncIterator[str]:
        async for chunk in sse_single_column(
            session,
            style_id,
            prompt,
            client=self._chat_client,
            executor=self._executor,
        ):
            yield chunk
