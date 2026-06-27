"""chat/generate_retry.py のユニットテスト。"""

from __future__ import annotations

import asyncio

from joryu.chat.generate_retry import chat_needs_retry, run_tool_loop_with_retry
from joryu.vllm_client import ChatResult


def test_chat_needs_retry_empty_answer() -> None:
    chat = ChatResult(
        thinking="思考",
        answer="",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
    )
    assert chat_needs_retry(chat) is True


def test_chat_needs_retry_ok_answer() -> None:
    chat = ChatResult(
        thinking="思考",
        answer="今日は晴れです。",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
    )
    assert chat_needs_retry(chat) is False


def test_run_tool_loop_with_retry_retries_on_empty_answer() -> None:
    calls = {"n": 0}

    async def run_once():
        calls["n"] += 1
        if calls["n"] == 1:
            chat = ChatResult(
                thinking="t",
                answer="",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )
        else:
            chat = ChatResult(
                thinking="t",
                answer="回答です。",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )
        yield {"type": "_tool_loop_done", "final_chat": chat, "turns": []}

    async def collect():
        events = []
        async for event in run_tool_loop_with_retry(run_once, max_attempts=2):
            events.append(event)
        return events

    events = asyncio.run(collect())
    assert calls["n"] == 2
    assert events[-1]["final_chat"].answer == "回答です。"
