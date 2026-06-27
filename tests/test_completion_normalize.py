"""completion_normalize.py のユニットテスト (#220 / #229, #230, #233)。"""

from __future__ import annotations

from joryu.completion_normalize import normalize_chat_result, sanitize_thinking_trace
from joryu.vllm_client import ChatResult

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


def test_normalize_extracts_bare_json_from_answer() -> None:
    """失敗 A: answer に raw JSON → tool_calls に転写し answer から除去。"""
    bare = '{"name": "weather", "arguments": {"location": "Tokyo", "date": "2026-06-27"}}'
    chat = ChatResult(
        thinking=None,
        answer=bare,
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        tool_calls=(),
        raw_completion=bare,
    )
    normalized = normalize_chat_result(chat, tools=_WEATHER_TOOLS)
    assert len(normalized.tool_calls) == 1
    assert normalized.tool_calls[0].name == "weather"
    assert '"name"' not in (normalized.answer or "")
    assert normalized.suspected_unparsed_tool_calls == ()


def test_normalize_extracts_json_from_thinking_when_answer_empty() -> None:
    """失敗 F/E: thinking 内 JSON + answer 空 → tool_calls 抽出。"""
    thinking = (
        "For each function call, return a json object with function name and arguments within\n"
        '{"name": "weather", "arguments": {"location": "Tokyo"}}'
    )
    chat = ChatResult(
        thinking=thinking,
        answer="",
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        tool_calls=(),
        raw_completion=f"<think>{thinking}</think>",
    )
    normalized = normalize_chat_result(chat, tools=_WEATHER_TOOLS)
    assert len(normalized.tool_calls) == 1
    assert normalized.tool_calls[0].name == "weather"


def test_normalize_records_suspected_when_unknown_tool() -> None:
    """失敗 H: 未登録ツール名の bare JSON は suspected に記録。"""
    bare = '{"name": "rm_rf", "arguments": {"path": "/"}}'
    chat = ChatResult(
        thinking=None,
        answer=bare,
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        tool_calls=(),
        raw_completion=bare,
    )
    normalized = normalize_chat_result(chat, tools=_WEATHER_TOOLS)
    assert normalized.tool_calls == ()
    assert normalized.suspected_unparsed_tool_calls
    assert any("rm_rf" in h for h in normalized.suspected_unparsed_tool_calls)


def test_sanitize_thinking_strips_meta_instruction() -> None:
    """失敗 D: 英語メタ命令断片を thinking から除去。"""
    thinking = (
        "For each function call, return a json object with function name and arguments within "
        "tool_call XML tags.\n\n実際の思考内容です。"
    )
    cleaned = sanitize_thinking_trace(thinking)
    assert "For each function call" not in cleaned
    assert "実際の思考内容" in cleaned


def test_normalize_sanitizes_thinking() -> None:
    chat = ChatResult(
        thinking="For each function call, return a json object.\n天気を調べます。",
        answer="回答",
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        tool_calls=(),
        raw_completion="",
    )
    normalized = normalize_chat_result(chat, tools=_WEATHER_TOOLS)
    assert normalized.thinking is not None
    assert "For each function call" not in normalized.thinking
    assert "天気を調べます" in normalized.thinking
