"""tools_impl.fetch のテスト。"""

from __future__ import annotations

import httpx
import pytest
import respx

from joryu.tools_impl.fetch import fetch_url


def test_fetch_url_rejects_non_http() -> None:
    with pytest.raises(ValueError, match="http/https"):
        fetch_url("file:///etc/passwd")


def test_fetch_url_rejects_private_ip() -> None:
    with pytest.raises(ValueError, match="blocked URL"):
        fetch_url("http://127.0.0.1/secret")


@respx.mock
def test_fetch_url_extracts_main_text() -> None:
    html = "<html><head><title>Sample</title></head><body><p>Hello world</p></body></html>"
    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text=html))
    out = fetch_url("https://example.com/page")
    assert "Sample" in out
    assert "Hello world" in out


@respx.mock
def test_fetch_url_truncates_large_response() -> None:
    big = "a" * 9000
    html = f"<html><body>{big}</body></html>"
    respx.get("https://example.com/big").mock(return_value=httpx.Response(200, text=html))
    out = fetch_url("https://example.com/big")
    assert out.endswith("[truncated]")


@respx.mock
def test_fetch_url_handles_timeout(monkeypatch) -> None:
    monkeypatch.setenv("JORYU_FETCH_TIMEOUT", "0.001")

    def _timeout_request(request):
        raise httpx.TimeoutException("timeout")

    respx.get("https://example.com/slow").mock(side_effect=_timeout_request)
    with pytest.raises(httpx.TimeoutException):
        fetch_url("https://example.com/slow")
