"""チャット生成の truncation / 空 answer リトライ (#232)。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from joryu.truncation import record_looks_truncated
from joryu.vllm_client import ChatResult

DEFAULT_MAX_ATTEMPTS = 2


def chat_needs_retry(chat: ChatResult) -> bool:
    """answer 空または truncation 疑いのとき再生成対象。"""
    if chat.finish_reason == "tool_loop_exhausted":
        return False
    if chat.tool_calls:
        return False
    if not (chat.answer or "").strip():
        return True
    record = {
        "answer": chat.answer,
        "finish_reason": chat.finish_reason,
        "thinking_trace": chat.thinking,
    }
    return record_looks_truncated(record)


async def run_tool_loop_with_retry(
    run_once: Callable[[], AsyncIterator[dict[str, Any]]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> AsyncIterator[dict[str, Any]]:
    """tool loop イベントストリームを truncation/空 answer 時に再試行する。"""
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        final_chat: ChatResult | None = None
        events: list[dict[str, Any]] = []
        async for event in run_once():
            if event.get("type") == "_tool_loop_done":
                final_chat = event["final_chat"]
            events.append(event)
        if final_chat is None or final_chat.finish_reason == "error":
            for event in events:
                yield event
            return
        if not chat_needs_retry(final_chat) or attempt >= max_attempts:
            for event in events:
                yield event
            return
    for event in events:
        yield event


__all__ = ["DEFAULT_MAX_ATTEMPTS", "chat_needs_retry", "run_tool_loop_with_retry"]
