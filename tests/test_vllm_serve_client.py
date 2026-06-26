"""vllm_serve_client.py: OpenAI 互換 vllm serve クライアントのユニットテスト。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from joryu.vllm_serve_client import VllmServeClient, openai_response_to_chat_result


class _OpenAIHandler(BaseHTTPRequestHandler):
    last_body: dict | None = None
    last_path: str = ""

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_POST(self) -> None:
        _OpenAIHandler.last_path = self.path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        _OpenAIHandler.last_body = json.loads(raw.decode("utf-8"))
        payload = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def openai_server() -> str:
    server = HTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_vllm_serve_client_posts_openai_chat_completions(openai_server: str) -> None:
    client = VllmServeClient(openai_server, model="test-model")
    result = client.chat_via_template(
        [{"role": "user", "content": "hi"}],
        enable_thinking=False,
        temperature=0.2,
        max_tokens=128,
    )
    assert result.answer == "hello"
    assert _OpenAIHandler.last_path == "/v1/chat/completions"
    assert _OpenAIHandler.last_body is not None
    assert _OpenAIHandler.last_body["model"] == "test-model"
    assert _OpenAIHandler.last_body["messages"][0]["content"] == "hi"
    assert _OpenAIHandler.last_body["temperature"] == 0.2
    assert _OpenAIHandler.last_body["max_tokens"] == 128
    assert _OpenAIHandler.last_body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "extra_body" not in _OpenAIHandler.last_body


def test_vllm_serve_client_sends_tool_choice_and_tools(openai_server: str) -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "web", "parameters": {}},
        }
    ]
    tool_choice = {"type": "function", "function": {"name": "search"}}
    client = VllmServeClient(openai_server, model="m")
    client.chat_via_template(
        [{"role": "user", "content": "q"}],
        tools=tools,
        tool_choice=tool_choice,
    )
    assert _OpenAIHandler.last_body is not None
    assert _OpenAIHandler.last_body["tools"] == tools
    assert _OpenAIHandler.last_body["tool_choice"] == tool_choice


def test_vllm_serve_client_sends_top_k_and_repetition_penalty_top_level(
    openai_server: str,
) -> None:
    """vllm serve は OpenAI 拡張パラメータをトップレベルで受け付ける。"""
    client = VllmServeClient(openai_server, model="m")
    client.chat_via_template(
        [{"role": "user", "content": "q"}],
        top_k=20,
        repetition_penalty=1.0,
    )
    body = _OpenAIHandler.last_body or {}
    assert body.get("top_k") == 20
    assert body.get("repetition_penalty") == 1.0
    assert "extra_body" not in body


def test_openai_response_to_chat_result_parses_reasoning_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "answer text",
                    "reasoning_content": "internal reasoning",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    result = openai_response_to_chat_result(data, effective_max_tokens=64)
    assert result.thinking == "internal reasoning"
    assert result.answer == "answer text"
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 2
    assert result.effective_max_tokens == 64
    assert "internal reasoning" in (result.raw_completion or "")


def test_openai_response_to_chat_result_parses_tool_calls() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search",
                                "arguments": '{"query": "東京 天気"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    result = openai_response_to_chat_result(data, effective_max_tokens=32)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "東京 天気"}
    assert result.finish_reason == "tool_calls"


def test_openai_response_to_chat_result_extracts_thinking_from_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>plan</think>\nfinal",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    result = openai_response_to_chat_result(data, effective_max_tokens=32)
    assert result.thinking == "plan"
    assert result.answer == "final"


def test_openai_response_malformed_tool_arguments() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "x",
                            "type": "function",
                            "function": {"name": "calc", "arguments": "not-json"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    result = openai_response_to_chat_result(data, effective_max_tokens=16)
    assert result.tool_calls[0].name == "<malformed>"
