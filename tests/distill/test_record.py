"""distill.record: JSONL レコード構築のテスト。"""

from __future__ import annotations

from joryu.core.prompt_bank import EffectiveSampling, PromptRow
from joryu.distill.record import build_record
from joryu.vllm.protocol import ChatResult


def _chat_result() -> ChatResult:
    return ChatResult(
        answer="回答",
        thinking="思考",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=2,
        tool_calls=[],
        raw_completion="raw",
        suspected_unparsed_tool_calls=[],
    )


def test_build_record_includes_mode_thinking() -> None:
    row = PromptRow(prompt="p", category="c")
    eff = EffectiveSampling(
        style_id="prose",
        system_prompt="sys",
        sampling={"temperature": 0.6},
        tools=[],
    )
    rec = build_record(
        row=row,
        eff=eff,
        thinking="思考",
        answer="回答",
        model_name="test-model",
        config_hash="sha256-abc",
        chat=_chat_result(),
    )
    assert rec["mode"] == "thinking"
