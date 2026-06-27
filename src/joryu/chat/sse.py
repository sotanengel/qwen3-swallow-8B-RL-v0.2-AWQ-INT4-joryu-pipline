"""チャット SSE フォーマットとストリーム merge。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from joryu.chat.session import ChatSession
from joryu.chat.streamer import stream_column_turn
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat, SupportsChatStream

DEFAULT_SAMPLING = {"temperature": 0.7, "top_p": 0.9}


def format_sse(event: dict[str, Any]) -> str:
    event_type = event.pop("type")
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _finalize_done(session_id: str) -> str:
    return format_sse({"type": "done", "session_id": session_id})


async def merge_streams(
    streams: list[tuple[str, AsyncIterator[dict[str, Any]]]],
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    total = len(streams)

    async def pump(column_id: str, stream: AsyncIterator[dict[str, Any]]) -> None:
        try:
            async for event in stream:
                await queue.put(event)
        except Exception as exc:
            await queue.put(
                {"type": "error", "column": column_id, "message": str(exc)},
            )
            await queue.put(
                {
                    "type": "column_done",
                    "column": column_id,
                    "finish_reason": "error",
                    "record_id": "",
                },
            )
        finally:
            await queue.put(None)

    tasks = [asyncio.create_task(pump(cid, s)) for cid, s in streams]
    done = 0
    while done < total:
        item = await queue.get()
        if item is None:
            done += 1
        else:
            yield item
    await asyncio.gather(*tasks, return_exceptions=True)


async def sse_all_columns(
    session: ChatSession,
    prompt: str,
    *,
    client: SupportsChat,
    executor: ToolExecutor | None,
    stream_client: SupportsChatStream | None = None,
    sampling: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    samp = sampling or DEFAULT_SAMPLING
    done_emitted = False
    try:
        streams = [
            (
                col.style_id,
                stream_column_turn(
                    session,
                    col,
                    prompt,
                    client=client,
                    executor=executor,
                    stream_client=stream_client,
                    sampling=samp,
                ),
            )
            for col in session.columns.values()
        ]
        async for event in merge_streams(streams):
            yield format_sse(dict(event))
        yield _finalize_done(session.session_id)
        done_emitted = True
    finally:
        if not done_emitted:
            yield _finalize_done(session.session_id)


async def sse_single_column(
    session: ChatSession,
    style_id: str,
    prompt: str,
    *,
    client: SupportsChat,
    executor: ToolExecutor | None,
    stream_client: SupportsChatStream | None = None,
    sampling: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    if style_id not in session.columns:
        yield format_sse({"type": "error", "message": f"unknown column: {style_id}"})
        yield _finalize_done(session.session_id)
        return
    samp = sampling or DEFAULT_SAMPLING
    column = session.columns[style_id]
    done_emitted = False
    try:
        async for event in stream_column_turn(
            session,
            column,
            prompt,
            client=client,
            executor=executor,
            stream_client=stream_client,
            sampling=samp,
        ):
            yield format_sse(dict(event))
        yield _finalize_done(session.session_id)
        done_emitted = True
    finally:
        if not done_emitted:
            yield _finalize_done(session.session_id)
