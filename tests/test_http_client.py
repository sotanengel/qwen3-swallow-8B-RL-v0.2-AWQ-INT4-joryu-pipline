"""http_client のテスト。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from joryu.http_client import (
    build_httpx_timeout,
    get_shared_async_client,
    reset_shared_async_client_for_tests,
)
from joryu.vllm_client import VllmError
from joryu.vllm_stream_client import VllmServeStreamClient


def test_build_httpx_timeout_sets_connect_and_read() -> None:
    timeout = build_httpx_timeout(read_s=120.0)
    assert timeout.connect == 5.0
    assert timeout.read == 120.0
    assert timeout.write == 5.0
    assert timeout.pool == 5.0


def test_shared_async_client_is_singleton() -> None:
    reset_shared_async_client_for_tests()
    first = get_shared_async_client(read_timeout_s=30.0)
    second = get_shared_async_client(read_timeout_s=30.0)
    assert first is second


def test_chat_stream_total_timeout_on_hanging_server() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        return httpx.Response(200, content=b"data: [DONE]\n\n")

    transport = httpx.MockTransport(handler)
    client = VllmServeStreamClient(
        "http://fake:8100",
        timeout_s=0.2,
        transport=transport,
    )

    async def _consume() -> None:
        async for _chunk in client.chat_stream([{"role": "user", "content": "hi"}]):
            pass

    with pytest.raises(VllmError, match="stream timed out"):
        asyncio.run(_consume())
