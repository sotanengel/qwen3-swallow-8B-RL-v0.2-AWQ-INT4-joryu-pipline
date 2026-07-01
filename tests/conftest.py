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
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
                "tools": tools,
                "tool_choice": tool_choice,
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


class FakeStreamClient:
    """SupportsChatStream 互換のテスト用 streaming クライアント。"""

    def __init__(
        self,
        answer: str = "回答",
        thinking: str | None = None,
        *,
        finish_reason: str = "stop",
        answers: list[str] | None = None,
        omit_done_chunk: bool = False,
        raise_runtime_error: bool = False,
        raise_after_n_chunks: int | None = None,
    ) -> None:
        self.answer = answer
        self.thinking = thinking
        self.finish_reason = finish_reason
        self.answers = answers
        self.omit_done_chunk = omit_done_chunk
        self.raise_runtime_error = raise_runtime_error
        self.raise_after_n_chunks = raise_after_n_chunks
        self.calls: list[dict[str, Any]] = []
        self._call_index = 0

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ):
        from joryu.vllm_stream_client import StreamChunk

        self.calls.append(
            {
                "messages": messages,
                "enable_thinking": enable_thinking,
                "tools": tools,
                "tool_choice": tool_choice,
                "sampling": dict(sampling_overrides),
            }
        )
        if self.answers is not None:
            answer = self.answers[min(self._call_index, len(self.answers) - 1)]
        else:
            answer = self.answer
        self._call_index += 1

        known = extract_known_tool_names(tools)
        tool_calls, cleaned_answer, diagnostics = extract_tool_calls_with_diagnostics(
            answer,
            known_tool_names=known or None,
        )
        if self.raise_runtime_error:
            raise RuntimeError("streaming chat failed")
        chunk_count = 0
        for i in range(0, len(cleaned_answer), 4):
            if self.raise_after_n_chunks is not None and chunk_count >= self.raise_after_n_chunks:
                raise RuntimeError("streaming chat interrupted")
            yield StreamChunk(kind="content", delta=cleaned_answer[i : i + 4])
            chunk_count += 1
        if self.omit_done_chunk:
            return
        result = ChatResult(
            thinking=self.thinking if enable_thinking is not False else None,
            answer=cleaned_answer,
            finish_reason=self.finish_reason,
            prompt_tokens=10,
            completion_tokens=5,
            effective_max_tokens=sampling_overrides.get("max_tokens"),
            tool_calls=tuple(tool_calls),
            raw_completion=answer,
            suspected_unparsed_tool_calls=tuple(
                diagnostics.get("suspected_unparsed_tool_calls", [])
            ),
        )
        yield StreamChunk(kind="done", finish_reason=self.finish_reason, result=result)


@pytest.fixture()
def fake_client() -> FakeVllmClient:
    return FakeVllmClient()


@pytest.fixture(autouse=True)
def orchestrator_fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """API / ジョブテストは tmp_path に compose が無いため fake backend を使う。"""
    monkeypatch.setenv("JORYU_ORCHESTRATOR_BACKEND", "fake")


@pytest.fixture()
def fake_judge():
    from joryu.curate.judge_client import FakeJudgeClient

    return FakeJudgeClient()
