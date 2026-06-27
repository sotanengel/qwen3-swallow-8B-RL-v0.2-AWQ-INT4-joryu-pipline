"""Judge クライアント (OpenAI 互換) のテスト。"""

from __future__ import annotations

import httpx
import respx

from joryu.curate.judge_client import (
    HEALTH_RUBRIC_KEYS,
    OpenAICompatibleJudgeClient,
    parse_health_rubric_response,
)


@respx.mock
def test_openai_compatible_health_rubric():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"L-01":5,"L-02":4,"L-03":4,"L-04":5,"L-05":4,"reason_brief":"ok"}'
                }
            }
        ]
    }
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = OpenAICompatibleJudgeClient(base_url="http://localhost:8080", model="test-model")
    out = client.score_health_rubric(
        "instruction",
        "response",
        health_prompt_template="inst={instruction} resp={response}",
    )
    assert out["L-01"] == 5
    assert out["reason_brief"] == "ok"


def test_parse_health_rubric_response_defaults():
    out = parse_health_rubric_response("not json")
    for k in HEALTH_RUBRIC_KEYS:
        assert out[k] == 3
