"""LLM-HEALTH シグナルのテスト。"""

from __future__ import annotations

from joryu.curate.judge_client import HEALTH_RUBRIC_KEYS, FakeJudgeClient
from joryu.curate.signals.llm_judge import LlmHealthRubric, truncate_for_health


def test_truncate_for_health_long_text():
    text = "a" * 2000
    out = truncate_for_health(text, max_each=100)
    assert out.startswith("a" * 100)
    assert out.endswith("a" * 100)
    assert "..." in out


def test_llm_health_rubric_signal():
    judge = FakeJudgeClient(health_scores={k: 5 for k in HEALTH_RUBRIC_KEYS})
    sig = LlmHealthRubric(
        judge=judge,
        version="health_rubric.ja.v1.0",
        prompt_template="eval {instruction} {response}",
    )
    rec = {
        "prompt": "質問",
        "answer": "回答です。",
        "thinking_trace": "考え中",
        "mode": "thinking",
    }
    result = sig.evaluate(rec)
    assert result.code == "LLM-HEALTH"
    assert result.score == 1.0
    assert result.hard_reject is False
    assert judge.health_calls
