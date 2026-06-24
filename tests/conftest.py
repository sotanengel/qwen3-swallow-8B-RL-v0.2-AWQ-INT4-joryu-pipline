"""共通テストフィクスチャ。"""

from __future__ import annotations

from typing import Any

import pytest

from joryu.vllm_client import ChatResult


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
        **sampling_overrides: Any,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
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
        return ChatResult(
            thinking=thinking_out,
            answer=answer,
            finish_reason=finish_reason,
            prompt_tokens=10,
            completion_tokens=5,
            effective_max_tokens=sampling_overrides.get("max_tokens"),
        )


@pytest.fixture()
def fake_client() -> FakeVllmClient:
    return FakeVllmClient()


@pytest.fixture()
def fake_judge():
    from joryu.curate.judge_client import FakeJudgeClient

    return FakeJudgeClient()
