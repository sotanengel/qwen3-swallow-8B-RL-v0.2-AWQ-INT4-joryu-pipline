"""Thinking runaway guard tests (#250)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from joryu.chat.thinking_guard import (
    strip_empty_thinking_tags,
)
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolUpstreamError
from joryu.vllm_client import ChatResult
from tests.conftest import FakeVllmClient

_WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Weather lookup",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]


class _RunawayStreamClient:
    def __init__(self, *, repeats: int = 20) -> None:
        self._repeats = repeats
        self.calls: list[dict[str, Any]] = []

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ):
        from joryu.vllm_stream_client import StreamChunk

        self.calls.append({"messages": messages})
        for _ in range(self._repeats):
            yield StreamChunk(kind="content", delta="</think>")
        result = ChatResult(
            thinking=None,
            answer="",
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            effective_max_tokens=None,
            tool_calls=(),
            raw_completion="",
            suspected_unparsed_tool_calls=(),
        )
        yield StreamChunk(kind="done", result=result)


class _UpstreamErrorExecutor:
    def run(self, call: ParsedToolCall) -> str:
        raise ToolUpstreamError(status=400, body='{"missing":["location"]}', url="http://x")


def test_strip_empty_thinking_tags() -> None:
    assert strip_empty_thinking_tags("</think>") == ""
    assert strip_empty_thinking_tags("hello") == "hello"


@pytest.mark.timeout(5)
def test_thinking_runaway_aborts_streaming_loop() -> None:
    stream_client = _RunawayStreamClient(repeats=20)
    client = FakeVllmClient(answers=["fallback"])

    async def _collect() -> list[dict]:
        runner = ToolLoopRunner(max_turns=1)
        events: list[dict] = []
        async for event in runner.run(
            column_id="dialog",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=None,
            executor=None,
            client=client,
            stream_client=stream_client,
            sampling={"temperature": 0.7},
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    assert any(e.get("type") == "error" for e in events)
    assert events[-1]["type"] == "_tool_loop_done"


@pytest.mark.timeout(5)
def test_tool_error_messages_exclude_empty_thinking_tags() -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    client = FakeVllmClient(answers=[weather_call, "取得できません。"])
    stream_client = _RunawayStreamClient(repeats=0)

    async def _collect() -> list[dict[str, Any]]:
        runner = ToolLoopRunner(max_turns=2)
        column_messages: list[dict[str, Any]] = []
        events: list[dict] = []
        async for event in runner.run(
            column_id="dialog",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=column_messages,
            tools=_WEATHER_TOOLS,
            executor=_UpstreamErrorExecutor(),
            client=client,
            stream_client=stream_client,
            sampling={"temperature": 0.7},
        ):
            events.append(event)
        return column_messages

    column_messages = asyncio.run(_collect())
    serialized = str(column_messages)
    assert "</think>" not in serialized
