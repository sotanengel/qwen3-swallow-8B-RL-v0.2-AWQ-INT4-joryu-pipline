"""Tool loop timeout/exception handling tests (#202)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from joryu.chat.tool_loop import ToolLoopRunner
from joryu.tool_calls import ParsedToolCall
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


class _RaisingExecutor:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def run(self, call: ParsedToolCall) -> str:
        raise self._exc


def _collect_tool_loop_events(exc: Exception) -> list[dict]:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    client = FakeVllmClient(answers=[weather_call, "今日は晴れです。"])
    executor = _RaisingExecutor(exc)

    async def _collect() -> list[dict]:
        runner = ToolLoopRunner(max_turns=2)
        events: list[dict] = []
        async for event in runner.run(
            column_id="prose",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=_WEATHER_TOOLS,
            executor=executor,
            client=client,
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events

    return asyncio.run(_collect())


@pytest.mark.parametrize(
    "exc",
    [
        httpx.TimeoutException("timeout"),
        httpx.ConnectError("connection refused"),
        httpx.HTTPStatusError(
            "server error",
            request=httpx.Request("GET", "http://example.com"),
            response=httpx.Response(503),
        ),
        KeyError("unknown tool"),
        ValueError("bad arguments"),
    ],
)
def test_tool_loop_emits_tool_error_and_completes(exc: Exception) -> None:
    events = _collect_tool_loop_events(exc)
    tool_errors = [e for e in events if e.get("type") == "tool_error"]
    assert len(tool_errors) == 1
    assert tool_errors[0]["name"] == "weather"
    assert tool_errors[0]["column"] == "prose"
    assert "message" in tool_errors[0]

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"].startswith("error:")

    assert events[-1]["type"] == "_tool_loop_done"
    assert not any(e.get("type") == "error" for e in events if e.get("type") != "tool_error")
