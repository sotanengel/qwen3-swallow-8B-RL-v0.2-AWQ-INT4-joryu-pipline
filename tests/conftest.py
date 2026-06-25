"""共通テストフィクスチャ。"""

from __future__ import annotations

from typing import Any

import pytest

from joryu.tool_calls import extract_tool_calls_with_diagnostics
from joryu.vllm_client import ChatResult, extract_known_tool_names


class FakeVllmClient:
    """SupportsChat 互換のテスト用クライアント。呼び出しを記録する。"""

    def __init__(
        self,
        answer: str = "回答",
        thinking: str | None = "思考",
        *,
        finish_reason: str = "stop",
        finish_reasons: list[str] | None = None,
        answers: list[str] | None = None,
    ) -> None:
        self.answer = answer
        self.thinking = thinking
        self.finish_reason = finish_reason
        self.finish_reasons = finish_reasons
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool | None = True,
        tools: list[dict[str, Any]] | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
                "tools": tools,
                "sampling": dict(sampling_overrides),
            }
        )
        idx = len(self.calls) - 1
        if self.finish_reasons is not None:
            finish_reason = self.finish_reasons[min(idx, len(self.finish_reasons) - 1)]
        else:
            finish_reason = self.finish_reason
        if self.answers is not None:
            answer = self.answers[min(idx, len(self.answers) - 1)]
        else:
            answer = self.answer
        if enable_thinking is False:
            thinking_out: str | None = None
        else:
            thinking_out = self.thinking
        known = extract_known_tool_names(tools)
        tool_calls, cleaned_answer, diagnostics = extract_tool_calls_with_diagnostics(
            answer,
            known_tool_names=known or None,
        )
        return ChatResult(
            thinking=thinking_out,
            answer=cleaned_answer,
            finish_reason=finish_reason,
            prompt_tokens=10,
            completion_tokens=5,
            effective_max_tokens=sampling_overrides.get("max_tokens"),
            tool_calls=tuple(tool_calls),
            raw_completion=answer,
            suspected_unparsed_tool_calls=tuple(
                diagnostics.get("suspected_unparsed_tool_calls", [])
            ),
        )


@pytest.fixture()
def fake_client() -> FakeVllmClient:
    return FakeVllmClient()


@pytest.fixture()
def fake_judge():
    from joryu.curate.judge_client import FakeJudgeClient

    return FakeJudgeClient()
