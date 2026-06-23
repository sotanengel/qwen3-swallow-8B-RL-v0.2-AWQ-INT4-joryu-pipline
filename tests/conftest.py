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
    ) -> None:
        self.answer = answer
        self.thinking = thinking
        self.calls: list[dict[str, Any]] = []

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        **sampling_overrides: Any,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
                "sampling": dict(sampling_overrides),
            }
        )
        thinking = self.thinking if enable_thinking else None
        return ChatResult(
            thinking=thinking,
            answer=self.answer,
            finish_reason="stop",
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
