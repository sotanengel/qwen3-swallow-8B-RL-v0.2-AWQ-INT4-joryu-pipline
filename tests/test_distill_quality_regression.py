"""失敗パターン A〜I の回帰テスト (#237)。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from joryu.chat.tool_loop import ToolLoopRunner
from joryu.completion_normalize import normalize_chat_result, sanitize_thinking_trace
from joryu.curate.signals.quality import (
    FactualHallucination,
    StyleFormat,
    ToolLeak,
    VirtualData,
)
from joryu.prompt_dedup import PromptDedupGuard
from joryu.vllm_client import ChatResult
from joryu.vllm_stream_client import _assemble_chat_result
from tests.conftest import FakeStreamClient, FakeVllmClient

_WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "天気",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
        },
    }
]


def test_failure_a_bare_json_to_tool_calls() -> None:
    bare = '{"name": "weather", "arguments": {"location": "Tokyo"}}'
    result = _assemble_chat_result(
        content=bare,
        thinking=None,
        finish_reason="stop",
        tool_calls=(),
        known_tool_names={"weather"},
        effective_max_tokens=512,
        tools=_WEATHER_TOOLS,
    )
    assert result.tool_calls
    assert '"name"' not in (result.answer or "")


def test_failure_h_suspected_unparsed_for_unknown_tool() -> None:
    bare = '{"name": "unknown_tool", "arguments": {}}'
    chat = ChatResult(
        thinking=None,
        answer=bare,
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
        raw_completion=bare,
    )
    normalized = normalize_chat_result(chat, tools=_WEATHER_TOOLS)
    sig = ToolLeak()
    record = {"suspected_unparsed_tool_calls": list(normalized.suspected_unparsed_tool_calls)}
    assert sig.evaluate(record).hard_reject is True


def test_failure_d_sanitize_thinking_meta() -> None:
    thinking = "For each function call, return a json object.\n日本語思考。"
    assert "For each function call" not in sanitize_thinking_trace(thinking)


def test_failure_b_c_r10_signals() -> None:
    fact = FactualHallucination()
    virt = VirtualData()
    assert fact.evaluate(
        {
            "tools": _WEATHER_TOOLS,
            "tool_calls": [],
            "answer": "晴れ、28℃です。",
        }
    ).hard_reject
    assert virt.evaluate({"answer": "仮想データとして記載します。"}).hard_reject


def test_failure_i_prose_markdown_rejected() -> None:
    sig = StyleFormat()
    assert sig.evaluate({"style_id": "prose", "answer": "- item\n- item2"}).hard_reject


def test_failure_g_prompt_dedup() -> None:
    guard = PromptDedupGuard(max_per_key=5)
    for _ in range(5):
        guard.record(prompt="今日の東京の天気は？", style_id="prose")
    assert guard.should_skip(prompt="今日の東京の天気は？", style_id="prose")


def test_failure_f_second_turn_tool_execution() -> None:
    from joryu.tool_executor import StubToolExecutor

    turn1 = '{"name": "weather", "arguments": {"location": "Tokyo"}}'
    turn2 = "東京は晴れです。"

    async def _run():
        runner = ToolLoopRunner(max_turns=3)
        events = []
        async for event in runner.run(
            column_id="prose",
            working_messages=[
                {"role": "system", "content": "base"},
                {"role": "user", "content": "天気"},
            ],
            column_messages=[],
            tools=_WEATHER_TOOLS,
            executor=StubToolExecutor({"weather": "晴れ"}),
            client=FakeVllmClient(answer="x"),
            stream_client=FakeStreamClient(answers=[turn1, turn2]),
            sampling={"temperature": 0.7, "top_p": 0.9},
        ):
            events.append(event)
        return events

    events = asyncio.run(_run())
    assert any(e.get("type") == "tool_call" for e in events)


def test_weather_prompt_all_styles_quality(tmp_path: Path) -> None:
    """Epic 検証: normalize 後 answer に raw JSON が残らない。"""
    styles = ["prose", "qa_short", "dialog", "report"]
    bare = '{"name": "weather", "arguments": {"location": "Tokyo", "date": "2026-06-27"}}'
    for style_id in styles:
        result = normalize_chat_result(
            ChatResult(
                thinking=None,
                answer=bare,
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(),
                raw_completion=bare,
            ),
            tools=_WEATHER_TOOLS,
        )
        assert result.tool_calls, f"{style_id}: tool_calls empty"
        assert '"name"' not in (result.answer or ""), f"{style_id}: raw JSON in answer"
        record = {
            "style_id": style_id,
            "answer": result.answer or "",
            "tools": _WEATHER_TOOLS,
            "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in result.tool_calls],
            "suspected_unparsed_tool_calls": list(result.suspected_unparsed_tool_calls),
        }
        assert VirtualData().evaluate(record).hard_reject is False
        dumped = json.dumps(record, ensure_ascii=False)
        assert "仮想データ" not in dumped
