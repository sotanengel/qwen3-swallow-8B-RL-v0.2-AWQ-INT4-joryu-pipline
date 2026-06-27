"""チャット streamer のテスト。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from joryu.chat.session import ChatColumn, ChatSession
from joryu.chat.streamer import stream_column_turn
from joryu.styles import StylePreset
from joryu.tool_executor import StubToolExecutor
from tests.conftest import FakeVllmClient


def _run(coro):
    return asyncio.run(coro)


def _make_session(tmp_path: Path) -> ChatSession:
    from joryu.chat.session import ChatSessionConfig, ChatSessionState

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
    return ChatSession(config=config, state=state)


def _stub_executor():
    return StubToolExecutor({"calc": "2"})


async def _collect(session, column, prompt, client, **kwargs):
    events = []
    executor = kwargs.pop("executor", _stub_executor())
    async for event in stream_column_turn(
        session,
        column,
        prompt,
        client=client,
        executor=executor,
        sampling={"temperature": 0.7, "top_p": 0.9},
        **kwargs,
    ):
        events.append(event)
    return events


def test_stream_with_stream_client(tmp_path: Path) -> None:
    from tests.conftest import FakeStreamClient

    session = _make_session(tmp_path)
    column = session.columns["prose"]
    client = FakeVllmClient(answer="unused", thinking=None)
    stream_client = FakeStreamClient(answer="streaming")
    events = _run(
        _collect(session, column, "hi", client, stream_client=stream_client),
    )
    types = [e["type"] for e in events]
    assert types[0] == "column_start"
    assert "token" in types
    assert types[-1] == "column_done"
    assert stream_client.calls


def test_stream_yields_token_then_column_done(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    column = session.columns["prose"]
    client = FakeVllmClient(answer="こんにちは", thinking=None)
    events = _run(_collect(session, column, "hi", client))
    types = [e["type"] for e in events]
    assert types[0] == "column_start"
    assert "turn_start" in types
    assert "token" in types
    assert types[-1] == "column_done"
    assert column.turn_index == 1
    assert len(column.messages) >= 2


def test_stream_tool_loop_events(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    column = session.columns["prose"]
    turn1 = '<tool_call>{"name":"calc","arguments":{"expression":"1+1"}}</tool_call>'
    client = FakeVllmClient(answers=[turn1, "答えは2"], thinking=None)
    events = _run(_collect(session, column, "計算", client))
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "column_done" in types
    assert tmp_path.joinpath("out.jsonl").read_text(encoding="utf-8").strip()


def test_stream_multi_turn_history(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    column = session.columns["prose"]
    client = FakeVllmClient(answers=["一", "二"], thinking=None)
    _run(_collect(session, column, "1", client))
    assert column.turn_index == 1
    _run(_collect(session, column, "2", client))
    assert column.turn_index == 2
    assert len(column.messages) == 4


def test_stream_tool_loop_exhausted(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    column = session.columns["prose"]
    tool_call = '<tool_call>{"name":"calc","arguments":{"expression":"1+1"}}</tool_call>'
    client = FakeVllmClient(answer=tool_call, thinking=None)
    events = _run(_collect(session, column, "x", client, max_turns=1))
    done = next(e for e in events if e["type"] == "column_done")
    assert done["finish_reason"] == "tool_loop_exhausted"


class _ErrorOnlyRunner:
    async def run(self, **kwargs):
        yield {"type": "error", "column": kwargs["column_id"], "message": "boom"}


def test_stream_emits_column_done_on_inner_error(tmp_path: Path, monkeypatch) -> None:
    from joryu.chat import streamer as streamer_mod

    session = _make_session(tmp_path)
    column = session.columns["prose"]
    client = FakeVllmClient(answer="hi", thinking=None)
    monkeypatch.setattr(streamer_mod, "ToolLoopRunner", lambda **kw: _ErrorOnlyRunner())

    events = _run(_collect(session, column, "hi", client))
    assert events[-1]["type"] == "column_done"
    assert events[-1]["finish_reason"] == "error"
    assert any(e.get("type") == "error" for e in events)


def test_stream_emits_column_done_when_final_chat_none(tmp_path: Path, monkeypatch) -> None:
    from joryu.chat import streamer as streamer_mod

    class _EmptyDoneRunner:
        async def run(self, **kwargs):
            if False:
                yield {}

    session = _make_session(tmp_path)
    column = session.columns["prose"]
    client = FakeVllmClient(answer="hi", thinking=None)
    monkeypatch.setattr(streamer_mod, "ToolLoopRunner", lambda **kw: _EmptyDoneRunner())

    events = _run(_collect(session, column, "hi", client))
    assert events[-1]["type"] == "column_done"
    assert events[-1]["finish_reason"] == "error"


def test_stream_system_prompt_contains_today_date(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from joryu import datetime_context as dt_ctx
    from joryu.chat.session import ChatSessionConfig, ChatSessionState

    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    date_line = dt_ctx.format_date_context_ja(fixed)
    preset = StylePreset(style_id="prose", label="散文", instruction="散文で。")
    col = ChatColumn(style_id="prose", label="散文")
    config = ChatSessionConfig(
        base_system_prompt=f"{date_line}\n\nbase",
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
    column = session.columns["prose"]
    client = FakeVllmClient(answer="ok", thinking=None)
    _run(_collect(session, column, "hi", client))
    system_msg = client.calls[0]["messages"][0]["content"]
    assert "2026年06月27日" in system_msg
