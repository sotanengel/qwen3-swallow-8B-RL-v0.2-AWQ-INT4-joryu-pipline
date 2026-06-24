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
