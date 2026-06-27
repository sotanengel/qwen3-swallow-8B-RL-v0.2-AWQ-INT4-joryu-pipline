"""ToolLoopRunner の error path テスト。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from joryu.chat.session import ChatColumn, ChatSession, ChatSessionConfig, ChatSessionState
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.styles import StylePreset
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
        expires_at=999999.0,
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
