"""共有 httpx クライアントと timeout 設定。"""

from __future__ import annotations

import httpx

DEFAULT_CONNECT_TIMEOUT_S = 5.0
DEFAULT_WRITE_TIMEOUT_S = 5.0
DEFAULT_POOL_TIMEOUT_S = 5.0
DEFAULT_READ_TIMEOUT_S = 600.0

_shared_async_client: httpx.AsyncClient | None = None


def build_httpx_timeout(*, read_s: float = DEFAULT_READ_TIMEOUT_S) -> httpx.Timeout:
    return httpx.Timeout(
        connect=DEFAULT_CONNECT_TIMEOUT_S,
        read=read_s,
        write=DEFAULT_WRITE_TIMEOUT_S,
        pool=DEFAULT_POOL_TIMEOUT_S,
    )


def get_shared_async_client(*, read_timeout_s: float = DEFAULT_READ_TIMEOUT_S) -> httpx.AsyncClient:
    """プロセス内共有 AsyncClient (接続プール再利用)。"""
    global _shared_async_client
    if _shared_async_client is None:
        _shared_async_client = httpx.AsyncClient(timeout=build_httpx_timeout(read_s=read_timeout_s))
    return _shared_async_client


async def close_shared_async_client() -> None:
    global _shared_async_client
    if _shared_async_client is not None:
        await _shared_async_client.aclose()
        _shared_async_client = None


def reset_shared_async_client_for_tests() -> None:
    """テスト用: 共有クライアント参照をクリア (aclose は呼ばない)。"""
    global _shared_async_client
    _shared_async_client = None
