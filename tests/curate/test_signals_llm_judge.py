"""LLM-RUBRIC シグナル + judge クライアントのテスト (R-11)。"""

from __future__ import annotations

import pytest

from joryu.curate.judge_client import (
    DEFAULT_RUBRIC_PROMPT,
    RUBRIC_KEYS,
    FakeJudgeClient,
    VllmJudgeClient,
    parse_pair_response,
    parse_rubric_response,
    parse_self_response,
)
from joryu.curate.signals.llm_judge import (
    LLMPairSignalContext,
    LLMRubricSignal,
    LLMSelfSignal,
)


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
    from joryu.vllm_client import ChatResult

    class StubChat:
        def __init__(self):
            self.calls = []

        def chat_via_template(self, messages, *, enable_thinking=True, **sampling):
            self.calls.append({"messages": messages, "enable_thinking": enable_thinking})
            return ChatResult(
                thinking=None,
                answer='{"accuracy":4,"completeness":4,"fluency":4,"instruction_following":4,"safety":4}',
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
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


# ---------- LLM-PAIR ----------


def test_parse_pair_response_valid():
    assert parse_pair_response('{"winner": "a"}') == "a"
    assert parse_pair_response('{"winner": "b"}') == "b"
    assert parse_pair_response('{"winner": "tie"}') == "tie"


def test_parse_pair_response_fallback_on_garbage():
    assert parse_pair_response("not json") == "tie"
    assert parse_pair_response('{"winner": "unknown"}') == "tie"


def test_fake_judge_compare_pair_default_tie():
    fj = FakeJudgeClient()
    assert fj.compare_pair("p", "a", "b") == "tie"
    assert fj.pair_calls == [{"prompt": "p", "a": "a", "b": "b"}]


def test_fake_judge_compare_pair_with_scorer():
    fj = FakeJudgeClient(pair_scorer=lambda p, a, b: "a" if len(a) > len(b) else "b")
    assert fj.compare_pair("p", "long", "x") == "a"


def test_llm_pair_context_pairwise_winrate():
    # 3 件のグループで、a > b > c となる scorer を仕込む
    def scorer(prompt: str, a: str, b: str):
        priority = {"A": 3, "B": 2, "C": 1}
        if priority[a] > priority[b]:
            return "a"
        if priority[a] < priority[b]:
            return "b"
        return "tie"

    fj = FakeJudgeClient(pair_scorer=scorer)
    ctx = LLMPairSignalContext(judge=fj)
    records = [
        {"prompt": "p", "answer": "A"},
        {"prompt": "p", "answer": "B"},
        {"prompt": "p", "answer": "C"},
    ]
    winrate = ctx.evaluate_group(records, [0, 1, 2])
    # A: 2/2 = 1.0, B: 1/2 = 0.5, C: 0/2 = 0.0
    assert winrate[0] == 1.0
    assert winrate[1] == 0.5
    assert winrate[2] == 0.0


def test_llm_pair_context_singleton_returns_one():
    fj = FakeJudgeClient()
    ctx = LLMPairSignalContext(judge=fj)
    winrate = ctx.evaluate_group([{"prompt": "p", "answer": "a"}], [0])
    assert winrate == {0: 1.0}
    assert fj.pair_calls == []  # 比較不要


# ---------- LLM-SELF ----------


def test_parse_self_response_valid():
    assert parse_self_response('{"score": 0.85}') == 0.85
    assert parse_self_response('{"score": 1}') == 1.0
    assert parse_self_response('{"score": -1}') == 0.0
    assert parse_self_response('{"score": 2}') == 1.0


def test_parse_self_response_fallback():
    assert parse_self_response("no json") == 0.5
    assert parse_self_response('{"score": "bad"}') == 0.5


def test_llm_self_signal_thinking_mode_uses_judge():
    fj = FakeJudgeClient(self_score=0.9)
    sig = LLMSelfSignal(judge=fj)
    r = sig.evaluate({"prompt": "p", "answer": "a", "thinking_trace": "t", "mode": "thinking"})
    assert r.score == 0.9
    assert r.hard_reject is False
    assert fj.self_calls[0]["prompt"] == "p"


def test_llm_self_signal_nothinking_skips_call():
    fj = FakeJudgeClient(self_score=0.1)
    sig = LLMSelfSignal(judge=fj, hard_min=0.5)
    r = sig.evaluate({"prompt": "p", "answer": "a", "mode": "nothinking"})
    assert r.score == 1.0
    assert r.hard_reject is False
    assert fj.self_calls == []


def test_llm_self_signal_hard_reject_below_min():
    fj = FakeJudgeClient(self_score=0.2)
    sig = LLMSelfSignal(judge=fj, hard_min=0.5)
    r = sig.evaluate({"prompt": "p", "answer": "a", "thinking_trace": "t", "mode": "thinking"})
    assert r.hard_reject is True


def test_vllm_judge_client_pair_calls_chat():
    from joryu.vllm_client import ChatResult

    class StubChat:
        def __init__(self):
            self.calls = []

        def chat_via_template(self, messages, *, enable_thinking=True, **sampling):
            self.calls.append({"messages": messages, "enable_thinking": enable_thinking})
            return ChatResult(
                thinking=None,
                answer='{"winner": "b"}',
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )

    chat = StubChat()
    judge = VllmJudgeClient(chat, rubric_prompt=DEFAULT_RUBRIC_PROMPT, judge_mode="nothinking")
    w = judge.compare_pair("p", "ans-a", "ans-b")
    assert w == "b"
    assert chat.calls[0]["enable_thinking"] is False


def test_vllm_judge_client_self_uses_thinking():
    from joryu.vllm_client import ChatResult

    class StubChat:
        def __init__(self):
            self.calls = []

        def chat_via_template(self, messages, *, enable_thinking=True, **sampling):
            self.calls.append({"enable_thinking": enable_thinking})
            return ChatResult(
                thinking=None,
                answer='{"score": 0.7}',
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )

    chat = StubChat()
    judge = VllmJudgeClient(chat, rubric_prompt=DEFAULT_RUBRIC_PROMPT, judge_mode="nothinking")
    s = judge.score_self_consistency("p", "thinking text", "answer text")
    assert s == 0.7
    # self_consistency は常に thinking モード固定
    assert chat.calls[0]["enable_thinking"] is True
