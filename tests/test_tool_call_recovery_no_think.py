"""tool_call_recovery: enable_thinking=False フォールバック (#111)。"""

from __future__ import annotations

from typing import Any

from joryu.tool_call_recovery import recover_tool_call
from joryu.vllm_client import ChatResult


class NoThinkFallbackClient:
    """named function (thinking) は失敗、no_think では tool_call 成功。"""

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
                "enable_thinking": enable_thinking,
                "tool_choice": tool_choice,
            }
        )
        if enable_thinking is False and tool_choice is not None:
            return ChatResult(
                thinking=None,
                answer="",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(ParsedToolCall(name="search", arguments={"query": "q"}, raw=""),),
            )
        if tool_choice is not None:
            return ChatResult(
                thinking="still planning",
                answer="",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(),
            )
        return ChatResult(
            thinking="I'll use the search function.",
            answer="",
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            tool_calls=(),
        )


def test_recover_tool_call_no_think_fallback_after_named_function_fails() -> None:
    client = NoThinkFallbackClient()
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    initial = client.chat_via_template(
        [{"role": "user", "content": "最新統計"}],
        tools=tools,
    )
    final, meta = recover_tool_call(
        client,
        initial,
        messages=[{"role": "user", "content": "最新統計"}],
        tools=tools,
        sampling={},
        max_attempts=1,
        no_think_fallback=True,
    )
    assert meta["no_think_fallback_used"] is True
    assert meta["no_think_fallback_succeeded"] is True
    assert meta["succeeded"] is True
    assert meta["method"] == "no_think_fallback"
    assert len(final.tool_calls) == 1
    assert client.calls[-1]["enable_thinking"] is False


def test_recover_tool_call_skips_no_think_when_disabled() -> None:
    client = NoThinkFallbackClient()
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    initial = client.chat_via_template(
        [{"role": "user", "content": "最新統計"}],
        tools=tools,
    )
    _final, meta = recover_tool_call(
        client,
        initial,
        messages=[{"role": "user", "content": "最新統計"}],
        tools=tools,
        sampling={},
        max_attempts=1,
        no_think_fallback=False,
    )
    assert meta["no_think_fallback_used"] is False
    assert meta["succeeded"] is False
    assert len(client.calls) == 2  # initial + 1 named retry only
