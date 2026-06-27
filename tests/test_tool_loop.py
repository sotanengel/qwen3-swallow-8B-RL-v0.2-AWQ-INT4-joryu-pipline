"""ToolLoopRunner の error path テスト。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from joryu.chat.session import ChatColumn, ChatSession, ChatSessionConfig, ChatSessionState
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.styles import StylePreset
from joryu.tool_executor import StubToolExecutor
from tests.conftest import FakeStreamClient, FakeVllmClient


def _run(coro):
    return asyncio.run(coro)


def _make_runner_events(**kwargs):
    async def _collect():
        runner = ToolLoopRunner(max_turns=2)
        events = []
        async for event in runner.run(
            column_id="prose",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=None,
            executor=None,
            client=FakeVllmClient(answer="unused"),
            sampling={"temperature": 0.7, "top_p": 0.9},
            **kwargs,
        ):
            events.append(event)
        return events

    return _run(_collect())


def test_tool_loop_streaming_error_still_emits_done() -> None:
    stream_client = FakeStreamClient(answer="x", omit_done_chunk=True)
    events = _make_runner_events(stream_client=stream_client)
    assert events[-1]["type"] == "_tool_loop_done"
    assert events[-1]["final_chat"].finish_reason == "error"
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1


def test_tool_loop_runtime_exception_emits_done() -> None:
    stream_client = FakeStreamClient(answer="x", raise_runtime_error=True)
    events = _make_runner_events(stream_client=stream_client)
    assert events[-1]["type"] == "_tool_loop_done"
    assert events[-1]["final_chat"].finish_reason == "error"
    assert any(e.get("type") == "error" for e in events)


def test_tool_loop_streaming_error_via_streamer_emits_column_done(tmp_path: Path) -> None:
    from joryu.chat.streamer import stream_column_turn

    preset = StylePreset(style_id="prose", label="散文", instruction="散文で。")
    col = ChatColumn(style_id="prose", label="散文")
    config = ChatSessionConfig(
        base_system_prompt="base",
        model_name="test-model",
        config_hash="hash",
        tools=(),
        tool_ids=(),
        out_path=tmp_path / "out.jsonl",
        style_presets={"prose": preset},
    )
    state = ChatSessionState(
        session_id="sess-1",
        columns={"prose": col},
        created_at=0.0,
        last_updated_at=0.0,
    )
    session = ChatSession(config=config, state=state)
    stream_client = FakeStreamClient(answer="x", omit_done_chunk=True)

    async def _collect():
        events = []
        async for event in stream_column_turn(
            session,
            col,
            "hi",
            client=FakeVllmClient(answer="unused"),
            stream_client=stream_client,
            executor=None,
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events

    events = _run(_collect())
    assert events[-1]["type"] == "column_done"
    assert events[-1]["finish_reason"] == "error"


_WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "天気",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]


def test_tool_loop_second_turn_bare_json_executes_tool() -> None:
    """失敗 F: 1 ターン目 bare JSON → tool 実行 → 2 ターン目で自然文回答。"""
    turn1 = '{"name": "weather", "arguments": {"location": "Tokyo"}}'
    turn2 = "東京は晴れで気温は25度です。"
    executor = StubToolExecutor({"weather": "晴れ 25℃"})

    async def _collect():
        runner = ToolLoopRunner(max_turns=3)
        events = []
        async for event in runner.run(
            column_id="prose",
            working_messages=[
                {"role": "system", "content": "base"},
                {"role": "user", "content": "今日の東京の天気は？"},
            ],
            column_messages=[],
            tools=_WEATHER_TOOLS,
            executor=executor,
            client=FakeVllmClient(answer="unused"),
            stream_client=FakeStreamClient(answers=[turn1, turn2]),
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events

    events = _run(_collect())
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls) >= 1
    assert tool_calls[0]["name"] == "weather"
    final = events[-1]["final_chat"]
    assert final.answer == turn2
