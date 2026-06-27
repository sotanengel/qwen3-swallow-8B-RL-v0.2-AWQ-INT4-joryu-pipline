"""MCP tool 4xx error body propagation tests (#248)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from joryu.chat.tool_loop import ToolLoopRunner
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import McpToolExecutor, ToolUpstreamError
from tests.conftest import FakeVllmClient

_WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Weather lookup",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["location"],
            },
        },
    }
]


class _UpstreamErrorExecutor:
    def run(self, call: ParsedToolCall) -> str:
        raise ToolUpstreamError(
            status=400,
            body='{"missing": ["location"], "hint": "provide location"}',
            url="http://localhost:8200/tools/weather",
        )


def _collect_tool_loop_events(
    *,
    executor: object,
    answers: list[str] | None = None,
) -> tuple[list[dict], list[dict[str, object]]]:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    client = FakeVllmClient(
        answers=answers or [weather_call, weather_call, "今日は晴れです。"],
    )
    column_messages: list[dict[str, object]] = []

    async def _collect() -> tuple[list[dict], list[dict[str, object]]]:
        runner = ToolLoopRunner(max_turns=3)
        events: list[dict] = []
        working: list[dict[str, object]] = [{"role": "system", "content": "base"}]
        async for event in runner.run(
            column_id="prose",
            working_messages=working,
            column_messages=column_messages,
            tools=_WEATHER_TOOLS,
            executor=executor,
            client=client,
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events, column_messages

    return asyncio.run(_collect())


def test_tool_upstream_error_in_sse_payload() -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    events, _ = _collect_tool_loop_events(
        executor=_UpstreamErrorExecutor(),
        answers=[weather_call, "取得できませんでした。"],
    )
    tool_errors = [e for e in events if e.get("type") == "tool_error"]
    assert len(tool_errors) == 1
    err = tool_errors[0]
    assert err["status"] == 400
    assert "missing" in err["body"]
    assert err["message"].startswith("HTTP 400")

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"].startswith("error: HTTP 400 —")


def test_tool_upstream_error_reaches_next_turn_messages() -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    events, column_messages = _collect_tool_loop_events(
        executor=_UpstreamErrorExecutor(),
        answers=[weather_call, "取得できませんでした。"],
    )
    tool_msgs = [m for m in column_messages if m.get("role") == "tool"]
    assert tool_msgs, "expected tool role message in column_messages"
    content = str(tool_msgs[0]["content"])
    assert content.startswith("error: HTTP 400 —")
    assert "missing" in content

    assert events[-1]["type"] == "_tool_loop_done"


@respx.mock
def test_mcp_executor_raises_tool_upstream_error_with_body() -> None:
    respx.post("http://localhost:8200/tools/weather").mock(
        return_value=httpx.Response(
            400,
            json={"missing": ["location"], "hint": "provide location"},
        )
    )
    executor = McpToolExecutor(url="http://localhost:8200")
    with pytest.raises(ToolUpstreamError) as exc_info:
        executor.run(
            ParsedToolCall(name="weather", arguments={"location": "東京"}, raw="{}"),
        )
    err = exc_info.value
    assert err.status == 400
    assert "missing" in err.body
    assert err.url.endswith("/tools/weather")


def test_tool_upstream_error_str_format() -> None:
    err = ToolUpstreamError(status=422, body='{"detail":"bad"}', url="http://x/y")
    assert str(err) == 'HTTP 422: {"detail":"bad"}'


def test_tool_upstream_error_json_body_parsed() -> None:
    payload = {"missing": ["location"], "hint": "x"}
    err = ToolUpstreamError(
        status=400,
        body=json.dumps(payload, ensure_ascii=False),
        url="http://x/y",
    )
    assert json.loads(err.body) == payload
