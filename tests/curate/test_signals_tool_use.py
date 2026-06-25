"""curate signals/tool_use.py: tool 品質ハード棄却。"""

from __future__ import annotations

from joryu.curate.signals.tool_use import ActionClaimWithoutCall, ToolPlannedNotCalled


def test_tool_planned_not_called_rejects_when_intent_without_call() -> None:
    signal = ToolPlannedNotCalled()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "回答",
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "tool_calls": [],
            "thinking_trace": "I'll use the search function to look this up.",
        }
    )
    assert result.hard_reject is True
    assert result.code == "TOOL-PLAN"


def test_tool_planned_not_called_passes_when_call_present() -> None:
    signal = ToolPlannedNotCalled()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "a",
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "tool_calls": [{"name": "search", "arguments": {"query": "x"}}],
            "thinking_trace": "search function",
        }
    )
    assert result.hard_reject is False


def test_tool_planned_not_called_passes_without_tools() -> None:
    signal = ToolPlannedNotCalled()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "a",
            "thinking_trace": "search function",
        }
    )
    assert result.hard_reject is False


def test_action_claim_without_call_rejects_fabricated_search() -> None:
    signal = ActionClaimWithoutCall()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "ウェブを検索した結果、再犯率は約20%です。",
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "tool_calls": [],
        }
    )
    assert result.hard_reject is True
    assert result.code == "TOOL-CLAIM"


def test_action_claim_without_call_passes_when_tool_called() -> None:
    signal = ActionClaimWithoutCall()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "検索した結果、再犯率は約20%です。",
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "tool_calls": [{"name": "search", "arguments": {"query": "x"}}],
        }
    )
    assert result.hard_reject is False


def test_action_claim_without_call_passes_plain_answer() -> None:
    signal = ActionClaimWithoutCall()
    result = signal.evaluate(
        {
            "prompt": "p",
            "answer": "一般知識として、再犯率は状況により異なります。",
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "tool_calls": [],
        }
    )
    assert result.hard_reject is False
