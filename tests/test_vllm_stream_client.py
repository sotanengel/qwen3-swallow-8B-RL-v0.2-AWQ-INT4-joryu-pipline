"""VllmServeStreamClient のテスト (#174)。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from joryu.vllm_stream_client import (
    StreamChunk,
    ToolCallStreamAccumulator,
    VllmServeStreamClient,
    openai_sse_data_to_chunks,
    parse_openai_sse_data,
)


def _run(coro):
    return asyncio.run(coro)


def test_parse_openai_sse_data_content_delta() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "hello"}}]})
    chunks = parse_openai_sse_data(payload)
    assert chunks == [StreamChunk(kind="content", delta="hello")]


def test_parse_openai_sse_data_reasoning_delta() -> None:
    payload = json.dumps({"choices": [{"delta": {"reasoning_content": "think"}}]})
    chunks = parse_openai_sse_data(payload)
    assert chunks == [StreamChunk(kind="thinking", delta="think")]


def test_parse_openai_sse_data_tool_call_partial() -> None:
    payload = json.dumps(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_abc",
                                "function": {"name": "search", "arguments": '{"q'},
                            }
                        ]
                    }
                }
            ]
        }
    )
    chunks = parse_openai_sse_data(payload)
    assert len(chunks) == 1
    assert chunks[0].kind == "tool_call_partial"
    assert chunks[0].tool_call_index == 0
    assert chunks[0].tool_call_id == "call_abc"
    assert chunks[0].tool_call_name == "search"
    assert chunks[0].tool_call_arguments_delta == '{"q'


def test_tool_call_accumulator_builds_parsed_calls() -> None:
    acc = ToolCallStreamAccumulator()
    acc.feed(
        tool_call_index=0,
        call_id="call_abc",
        name="search",
        arguments_delta='{"query":"x"}',
    )
    calls = acc.finalize()
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {"query": "x"}


def test_openai_sse_data_to_chunks_done() -> None:
    chunks = openai_sse_data_to_chunks("[DONE]")
    assert chunks == [StreamChunk(kind="done")]


async def _collect_stream(client: VllmServeStreamClient) -> list[StreamChunk]:
    chunks: list[StreamChunk] = []
    async for chunk in client.chat_stream(
        [{"role": "user", "content": "hi"}],
        enable_thinking=True,
    ):
        chunks.append(chunk)
    return chunks


def test_chat_stream_yields_content_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    sse_body = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content.decode())
        assert body["stream"] is True
        assert body["chat_template_kwargs"] == {"enable_thinking": True}
        return httpx.Response(200, content=sse_body.encode())

    transport = httpx.MockTransport(handler)
    client = VllmServeStreamClient(
        "http://fake:8100",
        model="test-model",
        transport=transport,
    )
    chunks = _run(_collect_stream(client))
    kinds = [c.kind for c in chunks]
    assert kinds.count("content") == 2
    assert kinds[-1] == "done"
    assert chunks[-1].result is not None
    assert chunks[-1].result.answer == "Hello"


def test_chat_stream_accumulates_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    sse_body = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_x",'
        '"function":{"name":"calc","arguments":""}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"{\\"expression\\":\\"1+1\\"}"}}]}}]}\n\n'
        'data: {"choices":[{"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body.encode())

    transport = httpx.MockTransport(handler)
    client = VllmServeStreamClient("http://fake:8100", transport=transport)
    chunks = _run(_collect_stream(client))
    result = chunks[-1].result
    assert result is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "calc"
    assert result.tool_calls[0].arguments == {"expression": "1+1"}
