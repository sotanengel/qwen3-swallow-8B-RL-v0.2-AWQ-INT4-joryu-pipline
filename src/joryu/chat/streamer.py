"""チャット SSE ストリーミング (tool loop 含む)。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from joryu.chat.generate_retry import chat_needs_retry, run_tool_loop_with_retry
from joryu.chat.session import ChatColumn, ChatSession
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.chat.turn_persistence import TurnPersistence
from joryu.styles import StylePreset
from joryu.system_prompt import build_system_prompt
from joryu.tool_executor import ToolExecutor
from joryu.tools import ToolDefinition
from joryu.vllm_client import SupportsChat, SupportsChatStream

DEFAULT_MAX_TURNS = 4
_FINISH_REASON_ERROR = "error"


def build_column_system_prompt(
    *,
    base_system_prompt: str,
    tool_defs: list[ToolDefinition] | None,
    style_preset: StylePreset,
) -> str:
    """列ごとの system prompt。base には factual guard 済みのため再付与しない。"""
    return build_system_prompt(
        base=base_system_prompt,
        tool_defs=tool_defs or None,
        style_preset=style_preset,
        factual_guard=False,
    )


async def stream_column_turn(
    session: ChatSession,
    column: ChatColumn,
    user_text: str,
    *,
    client: SupportsChat,
    sampling: dict[str, Any],
    executor: ToolExecutor | None = None,
    stream_client: SupportsChatStream | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    tool_loop_dedupe: bool = True,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """1 列 1 ターン分をストリーム。完了時に JSONL へ 1 行追記。"""
    column_id = column.style_id
    emitted_column_done = False
    try:
        yield {"type": "column_start", "column": column_id}
        preset = session.style_presets[column_id]
        tool_defs = [
            ToolDefinition(
                name=str(d["name"]),
                description=str(d.get("description") or ""),
                parameters=d.get("parameters") or {"type": "object", "properties": {}},
                invocation_rule=d.get("invocation_rule"),
            )
            for d in session.config.tool_definitions
        ]
        system_prompt = build_column_system_prompt(
            base_system_prompt=session.base_system_prompt,
            tool_defs=tool_defs or None,
            style_preset=preset,
        )
        turn_index = column.turn_index
        column.messages.append({"role": "user", "content": user_text})

        runner = ToolLoopRunner(max_turns=max_turns, tool_loop_dedupe=tool_loop_dedupe)
        persistence = TurnPersistence()
        final_chat = None
        turns: list[dict[str, Any]] = []

        turn_messages_len = len(column.messages)

        async def _run_loop():
            del column.messages[turn_messages_len:]
            loop_working: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                *column.messages,
            ]
            async for event in runner.run(
                column_id=column_id,
                working_messages=loop_working,
                column_messages=column.messages,
                tools=session.tools or None,
                executor=executor,
                client=client,
                stream_client=stream_client,
                sampling=sampling,
                cancel_event=cancel_event,
            ):
                yield event

        async for event in run_tool_loop_with_retry(_run_loop):
            if event.get("type") == "_tool_loop_done":
                final_chat = event["final_chat"]
                turns = event["turns"]
                continue
            if event.get("type") == "error":
                yield event
                continue
            yield event

        if final_chat is None:
            yield {"type": "error", "column": column_id, "message": "no chat result"}
            return

        if final_chat.finish_reason == _FINISH_REASON_ERROR:
            return

        if chat_needs_retry(final_chat):
            yield {
                "type": "error",
                "column": column_id,
                "message": "empty or truncated answer after retries",
            }
            return

        column.turn_index += 1
        _record, rec_id = persistence.persist_turn(
            session=session,
            style_id=column_id,
            system_prompt=system_prompt,
            user_text=user_text,
            turn_index=turn_index,
            final_chat=final_chat,
            turns=turns,
            sampling=sampling,
        )

        yield {
            "type": "column_done",
            "column": column_id,
            "finish_reason": final_chat.finish_reason,
            "record_id": rec_id,
        }
        emitted_column_done = True
    finally:
        if not emitted_column_done:
            yield {
                "type": "column_done",
                "column": column_id,
                "finish_reason": _FINISH_REASON_ERROR,
                "record_id": "",
            }
