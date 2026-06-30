"""vLLM prompt token 推定とコンテキスト予算のユニットテスト。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from joryu.vllm.common import (
    clamp_max_tokens_for_context,
    is_context_length_error,
    parse_context_overflow_input_tokens,
    resolve_serve_effective_max_tokens,
)
from joryu.vllm.protocol import VllmError
from joryu.vllm.serve import VllmServeClient


def test_is_context_length_error() -> None:
    assert is_context_length_error("maximum context length is 4096")
    assert is_context_length_error('{"input_tokens": 2049}')
    assert not is_context_length_error("connection reset")


def test_resolve_serve_effective_max_tokens_without_max_model_len() -> None:
    effective, prompt_tokens = resolve_serve_effective_max_tokens(
        messages=[{"role": "user", "content": "hi"}],
        model_path="m",
        requested_max_tokens=2048,
        max_model_len=None,
        enable_thinking=True,
        tools=None,
    )
    assert effective == 2048
    assert prompt_tokens is None


def test_estimate_chat_prompt_tokens_with_mock_tokenizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    import joryu.vllm.prompt_tokens as pt

    class _FakeTokenizer:
        def apply_chat_template(self, **kwargs: object) -> list[int]:
            return [1, 2, 3, 4, 5]

    class _FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(model_path: str, **kwargs: object) -> _FakeTokenizer:
            return _FakeTokenizer()

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoTokenizer = _FakeAutoTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    pt._tokenizer_cache.clear()

    assert (
        pt.estimate_chat_prompt_tokens(
            [{"role": "user", "content": "hi"}],
            model_path="fake-model",
            enable_thinking=False,
            tools=None,
        )
        == 5
    )


def test_estimate_chat_prompt_tokens_returns_none_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import sys

    import joryu.vllm.prompt_tokens as pt

    real_import = builtins.__import__

    def _fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: object = (),
        level: int = 0,
    ) -> object:
        if name == "transformers":
            raise ImportError("no transformers")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    monkeypatch.delitem(sys.modules, "transformers", raising=False)
    pt._tokenizer_cache.clear()
    assert (
        pt.estimate_chat_prompt_tokens(
            [{"role": "user", "content": "hi"}],
            model_path="missing",
            enable_thinking=True,
            tools=None,
        )
        is None
    )


def test_clamp_max_tokens_for_context_with_estimate() -> None:
    assert (
        clamp_max_tokens_for_context(
            requested_max_tokens=2048,
            max_model_len=4096,
            prompt_tokens=2049,
        )
        == 2015
    )


def test_clamp_max_tokens_for_context_without_estimate() -> None:
    assert (
        clamp_max_tokens_for_context(
            requested_max_tokens=2048,
            max_model_len=4096,
            prompt_tokens=None,
        )
        == 2048
    )


def test_clamp_max_tokens_for_context_raises_when_prompt_too_long() -> None:
    with pytest.raises(VllmError, match="prompt too long"):
        clamp_max_tokens_for_context(
            requested_max_tokens=2048,
            max_model_len=4096,
            prompt_tokens=4010,
        )


def test_parse_context_overflow_input_tokens_from_message() -> None:
    detail = (
        '{"error":{"message":"This model\'s maximum context length is 4096 tokens. '
        "However, your request has 4097 input tokens. "
        "Please reduce the length of the input messages. "
        'None: prompt contains at least 2049 input tokens"}}'
    )
    assert parse_context_overflow_input_tokens(detail) == 2049


def test_parse_context_overflow_input_tokens_returns_none_for_unrelated() -> None:
    assert parse_context_overflow_input_tokens("internal server error") is None


class _ContextOverflowHandler(BaseHTTPRequestHandler):
    call_count = 0
    last_body: dict | None = None

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_POST(self) -> None:
        _ContextOverflowHandler.call_count += 1
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        _ContextOverflowHandler.last_body = json.loads(raw.decode("utf-8"))
        if _ContextOverflowHandler.call_count == 1:
            err = {
                "error": {
                    "message": (
                        "This model's maximum context length is 4096 tokens. "
                        "However, your request has 4097 input tokens. "
                        "None: prompt contains at least 2049 input tokens"
                    ),
                    "type": "BadRequestError",
                    "code": 400,
                }
            }
            body = json.dumps(err).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        payload = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2049, "completion_tokens": 10},
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def overflow_server() -> str:
    _ContextOverflowHandler.call_count = 0
    _ContextOverflowHandler.last_body = None
    server = HTTPServer(("127.0.0.1", 0), _ContextOverflowHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_vllm_serve_client_retries_on_context_overflow_when_estimate_failed(
    monkeypatch: pytest.MonkeyPatch,
    overflow_server: str,
) -> None:
    monkeypatch.setattr(
        "joryu.vllm.prompt_tokens.estimate_chat_prompt_tokens",
        lambda *args, **kwargs: None,
    )
    client = VllmServeClient(overflow_server, model="m", max_model_len=4096)
    result = client.chat_via_template(
        [{"role": "user", "content": "long prompt"}],
        max_tokens=2048,
    )
    assert result.answer == "ok"
    assert _ContextOverflowHandler.call_count == 2
    assert _ContextOverflowHandler.last_body is not None
    assert _ContextOverflowHandler.last_body["max_tokens"] == 2015
