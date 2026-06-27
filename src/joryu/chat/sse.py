"""チャット SSE フォーマットとストリーム merge。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from joryu.chat.session import ChatSession
from joryu.chat.streamer import stream_column_turn
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat, SupportsChatStream

DEFAULT_SAMPLING = {"temperature": 0.7, "top_p": 0.9}
HEARTBEAT_INTERVAL_SEC = 5.0
HEARTBEAT_SSE = ": ping\n\n"

logger = logging.getLogger(__name__)


def format_sse(event: dict[str, Any]) -> str:
    event_type = event.pop("type")
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _finalize_done(session_id: str) -> str:
    return format_sse({"type": "done", "session_id": session_id})


async def with_heartbeat(
    stream: AsyncIterator[str],
    *,
    interval: float | None = None,
) -> AsyncIterator[str]:
    """長時間無音を防ぐ SSE コメント heartbeat を merge する。"""
    heartbeat_interval = HEARTBEAT_INTERVAL_SEC if interval is None else interval
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
    finished = False

    async def pump_events() -> None:
        nonlocal finished
        try:
            async for item in stream:
                await queue.put(("event", item))
        finally:
            finished = True
            await queue.put(("done", None))

    async def pump_heartbeat() -> None:
        while not finished:
            await asyncio.sleep(heartbeat_interval)
            if not finished:
                await queue.put(("ping", HEARTBEAT_SSE))

    event_task = asyncio.create_task(pump_events())
    heartbeat_task = asyncio.create_task(pump_heartbeat())
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "done":
                break
            if payload is not None:
                yield payload
    finally:
        finished = True
        heartbeat_task.cancel()
        await asyncio.gather(event_task, heartbeat_task, return_exceptions=True)


async def monitor_client_disconnect(
    request: Any,
    cancel_event: asyncio.Event,
    *,
    poll_interval: float = 0.5,
) -> None:
    """クライアント切断を検知して cancel_event を set する。"""
    is_disconnected = getattr(request, "is_disconnected", None)
    if not callable(is_disconnected):
        return
    while not cancel_event.is_set():
        if await is_disconnected():
            logger.info("client disconnected, cancelling tool task")
            cancel_event.set()
            return
        await asyncio.sleep(poll_interval)


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
    cancel_event: asyncio.Event | None = None,
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
                    cancel_event=cancel_event,
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
    cancel_event: asyncio.Event | None = None,
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
            cancel_event=cancel_event,
        ):
            yield format_sse(dict(event))
        yield _finalize_done(session.session_id)
        done_emitted = True
    finally:
        if not done_emitted:
            yield _finalize_done(session.session_id)
