"""prompt health rubric judge tests."""

from joryu.curate.judge_client import (
    PROMPT_HEALTH_RUBRIC_KEYS,
    FakeJudgeClient,
    parse_prompt_health_rubric_response,
)
from joryu.curate.signals.llm_judge import LlmPromptHealthRubric


def test_llm_prompt_health_rubric_evaluate() -> None:
    judge = FakeJudgeClient(prompt_health_scores={k: 5 for k in PROMPT_HEALTH_RUBRIC_KEYS})
    signal = LlmPromptHealthRubric(judge=judge, prompt_template="tpl")
    result = signal.evaluate({"prompt": "テストプロンプト"})
    assert result.code == "LLM-PROMPT-HEALTH"
    assert result.score == 1.0


def test_parse_prompt_health_rubric_response_defaults() -> None:
    out = parse_prompt_health_rubric_response("not json")
    assert out["P-01"] == 3
    assert out["reason_brief"] == "parse_failed"
