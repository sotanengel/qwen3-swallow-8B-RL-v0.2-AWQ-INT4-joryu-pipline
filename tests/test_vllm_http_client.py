"""vllm_client.py: VllmHttpClient のユニットテスト。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from joryu.config import ModelConfig, VllmConfig
from joryu.vllm_client import VllmHttpClient, resolve_chat_client, resolve_vllm_serve_url


class _Handler(BaseHTTPRequestHandler):
    last_body: dict | None = None

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        _Handler.last_body = json.loads(raw.decode("utf-8"))
        payload = {
            "thinking": "T",
            "answer": "A",
            "finish_reason": "stop",
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "effective_max_tokens": 64,
            "tool_calls": [],
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def http_server() -> str:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_vllm_http_client_posts_chat(http_server: str) -> None:
    client = VllmHttpClient(http_server)
    result = client.chat_via_template(
        [{"role": "user", "content": "hi"}],
        enable_thinking=False,
        temperature=0.2,
    )
    assert result.answer == "A"
    assert _Handler.last_body is not None
    assert _Handler.last_body["messages"][0]["content"] == "hi"
    assert _Handler.last_body["sampling"]["temperature"] == 0.2


def test_resolve_vllm_serve_url_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://joryu:8100")
    cfg = VllmConfig(serve_url="http://ignored")
    assert resolve_vllm_serve_url(cfg) == "http://joryu:8100"


def test_resolve_chat_client_uses_http_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://localhost:8100")
    client = resolve_chat_client(ModelConfig(), VllmConfig())
    assert isinstance(client, VllmHttpClient)
