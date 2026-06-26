"""チャット JSONL 永続化のテスト。"""

from __future__ import annotations

from dataclasses import asdict

from joryu.chat.persistence import build_chat_record
from joryu.styles import StylePreset, apply_style
from joryu.tool_calls import ParsedToolCall
from joryu.vllm_client import ChatResult


def test_build_chat_record_category_and_session_fields() -> None:
    preset = StylePreset(style_id="prose", label="散文", instruction="散文で。")
    _, system_prompt = apply_style("base", preset)
    chat = ChatResult(
        thinking="think",
        answer="答え",
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        tool_calls=(),
    )
    record = build_chat_record(
        prompt="質問",
        style_id="prose",
        system_prompt=system_prompt,
        session_id="sess-1",
        turn_index=2,
        thinking="think",
        answer="答え",
        model_name="test-model",
        config_hash="abc123",
        chat=chat,
        turns=[],
        sampling={"temperature": 0.7},
        tools=[],
        tool_ids=["search"],
    )
    assert record["category"] == "人間との対話"
    assert record["session_id"] == "sess-1"
    assert record["turn_index"] == 2
    assert record["style_id"] == "prose"
    assert record["system_prompt"] == "base\n\n散文で。"
    assert record["prompt"] == "質問"
    assert record["answer"] == "答え"


def test_build_chat_record_includes_tool_calls() -> None:
    call = ParsedToolCall(name="calc", arguments={"expression": "1+1"}, raw="")
    chat = ChatResult(
        thinking=None,
        answer="",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(call,),
    )
    record = build_chat_record(
        prompt="p",
        style_id="prose",
        system_prompt="sys",
        session_id="s",
        turn_index=0,
        thinking=None,
        answer="",
        model_name="m",
        config_hash="h",
        chat=chat,
        turns=[{"role": "assistant", "tool_calls": [asdict(call)]}],
        sampling={},
        tools=[{"type": "function"}],
        tool_ids=["calc"],
    )
    assert len(record["tool_calls"]) == 1
    assert record["tool_calls"][0]["name"] == "calc"
    assert record["turns"][0]["role"] == "assistant"
