"""Tool loop retry cap and circuit breaker tests (#252)."""

from __future__ import annotations

import asyncio
import time

import pytest

from joryu.chat.tool_loop import ToolLoopRunner
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolUpstreamError
from joryu.tool_pipeline.pipeline import normalize_tool_arguments, tool_call_dedupe_key
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

_ERROR_BODY = '{"missing": ["location"], "hint": "provide location"}'


class _CountingUpstreamErrorExecutor:
    def __init__(self) -> None:
        self.call_count = 0

    def run(self, call: ParsedToolCall) -> str:
        self.call_count += 1
        raise ToolUpstreamError(
            status=400,
            body=_ERROR_BODY,
            url="http://localhost:8200/tools/weather",
        )


def _weather_call(location: str) -> str:
    return f'<tool_call>{{"name":"weather","arguments":{{"location":"{location}"}}}}</tool_call>'


def _run_loop(
    *,
    answers: list[str],
    max_turns: int = 4,
) -> tuple[list[dict], _CountingUpstreamErrorExecutor]:
    executor = _CountingUpstreamErrorExecutor()
    client = FakeVllmClient(answers=answers)

    async def _collect() -> list[dict]:
        runner = ToolLoopRunner(max_turns=max_turns)
        events: list[dict] = []
        async for event in runner.run(
            column_id="report",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=_WEATHER_TOOLS,
            executor=executor,
            client=client,
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events

    return asyncio.run(_collect()), executor


@pytest.mark.timeout(5)
def test_identical_weather_error_deduped_to_single_executor_call() -> None:
    answers = [_weather_call("東京")] * 4 + ["ツールが使えません。"]
    events, executor = _run_loop(answers=answers)
    assert executor.call_count == 1
    tool_errors = [e for e in events if e.get("type") == "tool_error"]
    assert len(tool_errors) >= 1
    assert events[-1]["type"] == "_tool_loop_done"


@pytest.mark.timeout(5)
def test_whitespace_args_normalize_to_same_dedupe_key() -> None:
    call_a = ParsedToolCall(name="weather", arguments={"location": " 東京 "}, raw="{}")
    call_b = ParsedToolCall(name="weather", arguments={"location": "東京"}, raw="{}")
    assert tool_call_dedupe_key(call_a) == tool_call_dedupe_key(call_b)


def test_normalize_tool_arguments_strips_and_drops_empty() -> None:
    assert normalize_tool_arguments({"location": " 東京 ", "date": ""}) == {
        "location": "東京",
    }


@pytest.mark.timeout(5)
def test_repeated_upstream_error_circuit_breaker_caps_executor_calls() -> None:
    answers = [
        _weather_call("東京"),
        _weather_call("大阪"),
        _weather_call("名古屋"),
        _weather_call("福岡"),
        "取得できません。",
    ]
    started = time.monotonic()
    events, executor = _run_loop(answers=answers, max_turns=4)
    elapsed = time.monotonic() - started
    assert elapsed < 5.0
    assert executor.call_count <= 2
    tool_errors = [e for e in events if e.get("type") == "tool_error"]
    assert len(tool_errors) <= 2
    final = events[-1]["final_chat"]
    assert final.finish_reason in {"stop", "tool_loop_exhausted", "tool_calls"}
