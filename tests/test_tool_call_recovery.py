"""tool_call_recovery.py: named function 強制リトライ。"""

from __future__ import annotations

from typing import Any

from joryu.tool_call_recovery import build_named_function_tool_choice, recover_tool_call
from joryu.vllm_client import ChatResult


class RecoveryFakeClient:
    """1 回目は intent のみ、2 回目 (tool_choice 付き) で tool_call を返す。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        from joryu.tool_calls import ParsedToolCall

        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
                "tools": tools,
                "tool_choice": tool_choice,
                "sampling": dict(sampling_overrides),
            }
        )
        if tool_choice is not None:
            return ChatResult(
                thinking=None,
                answer="",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(ParsedToolCall(name="search", arguments={"query": "q"}, raw=""),),
            )
        return ChatResult(
            thinking="I'll use the search function.",
            answer="検索しました。",
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            tool_calls=(),
        )


def test_build_named_function_tool_choice() -> None:
    assert build_named_function_tool_choice("search") == {
        "type": "function",
        "function": {"name": "search"},
    }


def test_recover_tool_call_retries_with_named_function() -> None:
    client = RecoveryFakeClient()
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    initial = client.chat_via_template(
        [{"role": "user", "content": "最新統計は？"}],
        tools=tools,
    )
    final, meta = recover_tool_call(
        client,
        initial,
        messages=[{"role": "user", "content": "最新統計は？"}],
        tools=tools,
        sampling={"temperature": 0.6},
    )
    assert meta["succeeded"] is True
    assert meta["method"] == "named_function"
    assert meta["attempts"] == 1
    assert meta["tool_name"] == "search"
    assert len(final.tool_calls) == 1
    assert client.calls[1]["tool_choice"] == {
        "type": "function",
        "function": {"name": "search"},
    }


def test_recover_tool_call_skips_when_not_needed() -> None:
    from joryu.tool_calls import ParsedToolCall

    client = RecoveryFakeClient()
    chat = ChatResult(
        thinking=None,
        answer="普通の回答",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(ParsedToolCall(name="search", arguments={}, raw=""),),
    )
    final, meta = recover_tool_call(
        client,
        chat,
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "search", "parameters": {}}}],
        sampling={},
    )
    assert final is chat
    assert meta["attempts"] == 0
    assert meta["succeeded"] is False
