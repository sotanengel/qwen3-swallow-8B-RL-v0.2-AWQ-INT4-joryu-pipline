"""JSONL tool_calls / tool_errors / mcp_status 永続化 (#296 / Epic #294 Sub#2)。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import respx

from joryu.chat.streamer import stream_column_turn
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import McpToolExecutor, ToolUpstreamError
from joryu.vllm_client import ChatResult
from tests.chat.test_think_leak_persistence import _make_dialog_session
from tests.conftest import FakeVllmClient


class _WeatherOkExecutor:
    def run(self, call: ParsedToolCall) -> str:
        return "東京都 港区: 晴れ 22.8℃"


class _WeatherUpstreamErrorExecutor:
    def run(self, call: ParsedToolCall) -> str:
        raise ToolUpstreamError(status=400, body='{"missing":["location"]}', url="http://x")


async def _persist_weather_turn(
    tmp_path: Path,
    *,
    answers: list[str],
    executor: object,
) -> dict:
    from joryu.chat.turn_persistence import TurnPersistence

    TurnPersistence.reset_dedup()
    session = _make_dialog_session(tmp_path)
    column = session.columns["dialog"]
    client = FakeVllmClient(answers=answers, thinking=None)
    async for _event in stream_column_turn(
        session,
        column,
        "今日の東京の天気は？",
        client=client,
        executor=executor,
        sampling={"temperature": 0.7, "top_p": 0.9},
    ):
        pass
    line = tmp_path.joinpath("out.jsonl").read_text(encoding="utf-8").strip()
    return json.loads(line)


def test_weather_success_persists_tool_calls(tmp_path: Path) -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    record = asyncio.run(
        _persist_weather_turn(
            tmp_path,
            answers=[weather_call, "今日の東京は晴れです。"],
            executor=_WeatherOkExecutor(),
        )
    )
    assert record["tool_calls"]
    assert record["tool_calls"][0]["name"] == "weather"
    assert record["tool_calls"][0]["arguments"] == {"location": "東京"}
    assert "22.8" in record["tool_calls"][0]["result_summary"]
    assert record["mcp_status"] == "down"
    assert record["tool_errors"] == []


def test_weather_400_persists_tool_errors(tmp_path: Path) -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    record = asyncio.run(
        _persist_weather_turn(
            tmp_path,
            answers=[weather_call, "取得できません。"],
            executor=_WeatherUpstreamErrorExecutor(),
        )
    )
    assert record["tool_errors"]
    err = record["tool_errors"][0]
    assert err["name"] == "weather"
    assert err["status"] == 400
    assert "missing" in (err["body"] or "")
    assert err["retry_count"] >= 1
    assert record["mcp_status"] == "down"


@respx.mock
def test_mcp_4xx_persists_degraded_status(tmp_path: Path) -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    respx.post("http://localhost:8200/tools/weather").mock(
        return_value=httpx.Response(400, json={"missing": ["location"]}),
    )
    executor = McpToolExecutor(url="http://localhost:8200")
    record = asyncio.run(
        _persist_weather_turn(
            tmp_path,
            answers=[weather_call, "取得できません。"],
            executor=executor,
        )
    )
    assert record["tool_errors"]
    assert record["tool_errors"][0]["status"] == 400
    assert record["mcp_status"] == "degraded"


@respx.mock
def test_mcp_fallback_persists_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    respx.post("http://localhost:8200/tools/weather").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    executor = McpToolExecutor(url="http://localhost:8200")
    record = asyncio.run(
        _persist_weather_turn(
            tmp_path,
            answers=[weather_call, "今日は晴れです。"],
            executor=executor,
        )
    )
    assert record["mcp_status"] == "fallback_local"
    assert record["tool_calls"]
    assert record["tool_calls"][0]["name"] == "weather"


def test_build_chat_record_defaults_tool_meta_fields() -> None:
    from joryu.chat.persistence import build_chat_record

    chat = ChatResult(
        thinking=None,
        answer="ok",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
    )
    record = build_chat_record(
        prompt="p",
        style_id="prose",
        system_prompt="sys",
        session_id="s",
        turn_index=0,
        thinking=None,
        answer="ok",
        model_name="m",
        config_hash="h",
        chat=chat,
        turns=[],
        sampling={},
        tools=[],
        tool_ids=[],
    )
    assert record["tool_errors"] == []
    assert record["mcp_status"] == "down"
