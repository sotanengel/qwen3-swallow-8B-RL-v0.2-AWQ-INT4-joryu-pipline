"""tool_intent.py: tool 使用意図検出。"""

from __future__ import annotations

from joryu.tool_calls import ParsedToolCall
from joryu.tool_intent import (
    infer_planned_tool_name,
    needs_tool_call_recovery,
    thinking_plans_tool_use,
)
from joryu.vllm_client import ChatResult


def test_thinking_plans_tool_use_detects_english_intent() -> None:
    assert thinking_plans_tool_use("I'll use the search function to look this up.")


def test_thinking_plans_tool_use_detects_japanese_intent() -> None:
    assert thinking_plans_tool_use("検索ツールで最新情報を確認します。")


def test_thinking_plans_tool_use_negative_for_plain_answer() -> None:
    assert not thinking_plans_tool_use("これは一般知識で答えられます。")


def test_infer_planned_tool_name_from_known_names() -> None:
    text = "We should call search with query about background music."
    assert infer_planned_tool_name(text, {"search", "calc"}) == "search"


def test_infer_planned_tool_name_prefers_longer_match() -> None:
    text = "fetch_url で本文を取得する。"
    assert infer_planned_tool_name(text, {"fetch", "fetch_url"}) == "fetch_url"


def test_needs_tool_call_recovery_when_intent_without_calls() -> None:
    chat = ChatResult(
        thinking="I'll use the search function.",
        answer="調べます。",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
    )
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    assert needs_tool_call_recovery(chat, tools=tools)


def test_needs_tool_call_recovery_false_when_calls_present() -> None:
    chat = ChatResult(
        thinking="search を使う",
        answer="",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(ParsedToolCall(name="search", arguments={"query": "x"}, raw=""),),
    )
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    assert not needs_tool_call_recovery(chat, tools=tools)


def test_needs_tool_call_recovery_raw_tool_call_tag() -> None:
    chat = ChatResult(
        thinking=None,
        answer="回答",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
        raw_completion='<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>',
    )
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    assert needs_tool_call_recovery(chat, tools=tools)


def test_needs_tool_call_recovery_false_for_empty_tool_call_tag() -> None:
    chat = ChatResult(
        thinking=None,
        answer="あとがき",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
        raw_completion="<tool_call>{}</tool_call>\nあとがき",
        suspected_unparsed_tool_calls=("<tool_call>{}</tool_call>",),
    )
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    assert not needs_tool_call_recovery(chat, tools=tools)
