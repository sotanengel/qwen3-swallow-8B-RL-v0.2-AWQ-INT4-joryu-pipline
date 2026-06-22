"""LLM-RUBRIC シグナル + judge クライアントのテスト (R-11)。"""

from __future__ import annotations

import pytest

from joryu.curate.judge_client import (
    DEFAULT_RUBRIC_PROMPT,
    RUBRIC_KEYS,
    FakeJudgeClient,
    VllmJudgeClient,
    parse_rubric_response,
)
from joryu.curate.signals.llm_judge import LLMRubricSignal


def test_parse_rubric_response_clean_json():
    text = '{"accuracy":5,"completeness":4,"fluency":5,"instruction_following":4,"safety":5}'
    parsed = parse_rubric_response(text)
    assert parsed == {
        "accuracy": 5,
        "completeness": 4,
        "fluency": 5,
        "instruction_following": 4,
        "safety": 5,
    }


def test_parse_rubric_response_strips_code_fence():
    text = """```json
{"accuracy":3,"completeness":3,"fluency":3,"instruction_following":3,"safety":3}
```"""
    parsed = parse_rubric_response(text)
    assert all(parsed[k] == 3 for k in RUBRIC_KEYS)


def test_parse_rubric_response_handles_garbage():
    parsed = parse_rubric_response("blah blah no json here")
    # neutral fallback
    assert all(parsed[k] == 3 for k in RUBRIC_KEYS)


def test_parse_rubric_response_clamps_out_of_range():
    text = '{"accuracy":10,"completeness":0,"fluency":7,"instruction_following":-3,"safety":5}'
    parsed = parse_rubric_response(text)
    assert parsed["accuracy"] == 5
    assert parsed["completeness"] == 1
    assert parsed["fluency"] == 5
    assert parsed["instruction_following"] == 1


def test_fake_judge_records_calls():
    fj = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    out = fj.score_rubric("p", "a")
    assert out == {k: 5 for k in RUBRIC_KEYS}
    assert fj.calls == [{"prompt": "p", "answer": "a"}]


def test_llm_rubric_signal_normalizes_to_unit():
    fj = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})
    sig = LLMRubricSignal(judge=fj)
    r = sig.evaluate(
        {"prompt": "p", "answer": "a", "mode": "nothinking", "sampling": {}, "config_hash": "h"}
    )
    assert r.score == pytest.approx(1.0)
    assert r.hard_reject is False
    assert r.code == "LLM-RUBRIC"


def test_llm_rubric_signal_neutral_when_judge_fails():
    class BrokenJudge:
        def score_rubric(self, prompt: str, answer: str) -> dict[str, int]:
            return {k: 3 for k in RUBRIC_KEYS}

    sig = LLMRubricSignal(judge=BrokenJudge())
    r = sig.evaluate({"prompt": "p", "answer": "a"})
    assert r.score == pytest.approx(0.6)


def test_vllm_judge_client_calls_chat_with_no_thinking():
    class StubChat:
        def __init__(self):
            self.calls = []

        def chat_via_template(self, messages, *, enable_thinking=True, **sampling):
            self.calls.append({"messages": messages, "enable_thinking": enable_thinking})
            return (
                None,
                '{"accuracy":4,"completeness":4,"fluency":4,"instruction_following":4,"safety":4}',
            )

    chat = StubChat()
    judge = VllmJudgeClient(chat, rubric_prompt=DEFAULT_RUBRIC_PROMPT, judge_mode="nothinking")
    scores = judge.score_rubric("プロンプト", "回答")
    assert scores == {k: 4 for k in RUBRIC_KEYS}
    assert chat.calls[0]["enable_thinking"] is False
    assert chat.calls[0]["messages"][0]["role"] == "system"


def test_vllm_judge_client_neutral_on_chat_exception():
    class ErrChat:
        def chat_via_template(self, *args, **kwargs):
            raise RuntimeError("oops")

    judge = VllmJudgeClient(ErrChat(), rubric_prompt="x")
    scores = judge.score_rubric("p", "a")
    assert all(v == 3 for v in scores.values())
