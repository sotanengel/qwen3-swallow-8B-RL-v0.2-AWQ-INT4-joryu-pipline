"""チャット SSE ストリーミング (tool loop 含む)。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from joryu.chat.session import ChatColumn, ChatSession
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.chat.turn_persistence import TurnPersistence
from joryu.styles import apply_style
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat, SupportsChatStream

DEFAULT_MAX_TURNS = 4
_FINISH_REASON_ERROR = "error"


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
) -> AsyncIterator[dict[str, Any]]:
    """1 列 1 ターン分をストリーム。完了時に JSONL へ 1 行追記。"""
    column_id = column.style_id
    emitted_column_done = False
    try:
        yield {"type": "column_start", "column": column_id}
        preset = session.style_presets[column_id]
        _style_id, system_prompt = apply_style(session.base_system_prompt, preset)
        turn_index = column.turn_index
        column.messages.append({"role": "user", "content": user_text})

        working_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *column.messages,
        ]

        runner = ToolLoopRunner(max_turns=max_turns, tool_loop_dedupe=tool_loop_dedupe)
        persistence = TurnPersistence()
        final_chat = None
        turns: list[dict[str, Any]] = []

        async for event in runner.run(
            column_id=column_id,
            working_messages=working_messages,
            column_messages=column.messages,
            tools=session.tools or None,
            executor=executor,
            client=client,
            stream_client=stream_client,
            sampling=sampling,
        ):
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
