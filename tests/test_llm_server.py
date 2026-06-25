"""llm_server.py: vLLM 常駐デーモンの HTTP API テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from joryu.llm_server import create_llm_app, warmup_client
from tests.conftest import FakeVllmClient


def test_health_returns_503_before_loaded() -> None:
    fake = FakeVllmClient()
    app = create_llm_app(fake, model_loaded=False)
    tc = TestClient(app, raise_server_exceptions=False)
    resp = tc.get("/health")
    assert resp.status_code == 503


def test_health_returns_ok_when_loaded() -> None:
    fake = FakeVllmClient()
    app = create_llm_app(fake, model_loaded=True)
    tc = TestClient(app)
    resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "model_loaded": True}


def test_chat_endpoint_delegates_to_client() -> None:
    fake = FakeVllmClient(answer="hello", thinking="think")
    app = create_llm_app(fake, model_loaded=True)
    tc = TestClient(app)
    resp = tc.post(
        "/v1/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "enable_thinking": True,
            "sampling": {"temperature": 0.5},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "hello"
    assert body["thinking"] == "think"
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "hi"}]
    assert fake.calls[0]["enable_thinking"] is True
    assert fake.calls[0]["sampling"]["temperature"] == 0.5


def test_warmup_invokes_chat() -> None:
    fake = FakeVllmClient(answer="warm")
    warmup_client(fake)
    assert len(fake.calls) == 1
    assert fake.calls[0]["messages"][0]["role"] == "user"


def test_chat_endpoint_accepts_assistant_tool_calls_list() -> None:
    """tool-loop の 2 ターン目で送る assistant.tool_calls 配列を 422 にしない。

    回帰テスト: ChatRequest.messages の型が ``list[dict[str, str]]`` だった頃は、
    pydantic が ``tool_calls`` を string と判定して 422 を返し、tool-loop と
    ``recover_tool_call`` の named function 強制リトライが両方失敗していた。
    """
    fake = FakeVllmClient(answer="final")
    app = create_llm_app(fake, model_loaded=True)
    tc = TestClient(app)
    resp = tc.post(
        "/v1/chat",
        json={
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "天気は?"},
                {
                    "role": "assistant",
                    "content": "調べます",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search",
                                "arguments": '{"query": "東京 天気"}',
                            }
                        }
                    ],
                },
                {"role": "tool", "name": "search", "content": "晴れ"},
            ],
            "enable_thinking": True,
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "search", "description": "web", "parameters": {}},
                }
            ],
            "sampling": {},
        },
    )
    assert resp.status_code == 200, resp.text
    forwarded = fake.calls[-1]["messages"]
    assert forwarded[2]["role"] == "assistant"
    assert isinstance(forwarded[2]["tool_calls"], list)


def test_chat_endpoint_accepts_tool_choice_named_function() -> None:
    """recover_tool_call が送る ``tool_choice`` (dict 形式) も 422 にしない。"""
    fake = FakeVllmClient(answer="ok")
    app = create_llm_app(fake, model_loaded=True)
    tc = TestClient(app)
    resp = tc.post(
        "/v1/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "enable_thinking": True,
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "search", "description": "", "parameters": {}},
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "search"}},
            "sampling": {},
        },
    )
    assert resp.status_code == 200, resp.text
    assert fake.calls[-1].get("tool_choice") == {
        "type": "function",
        "function": {"name": "search"},
    }
