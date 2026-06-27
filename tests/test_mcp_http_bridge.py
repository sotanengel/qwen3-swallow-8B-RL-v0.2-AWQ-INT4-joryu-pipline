"""MCP HTTP bridge (/health, /tools/*) のテスト。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def bridge_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    from joryu.mcp.http_bridge import create_http_app

    return TestClient(create_http_app())


def test_mcp_http_health(bridge_client: TestClient) -> None:
    resp = bridge_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_mcp_http_weather(bridge_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "joryu.mcp.http_bridge.weather_impl",
        lambda location, date=None: f"{location}: 晴れ",
    )
    resp = bridge_client.post("/tools/weather", json={"location": "Tokyo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "Tokyo: 晴れ"


def test_mcp_http_web_search(bridge_client: TestClient) -> None:
    resp = bridge_client.post(
        "/tools/web_search",
        json={"query": "test", "top_k": 2},
    )
    assert resp.status_code == 200
    assert "stub" in resp.json()["result"].lower()


def test_mcp_http_unknown_tool(bridge_client: TestClient) -> None:
    resp = bridge_client.post("/tools/nope", json={})
    assert resp.status_code == 404


def test_mcp_http_timeout_error_returns_504(
    bridge_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _timeout(_args: dict) -> str:
        raise TimeoutError("upstream timed out")

    monkeypatch.setitem(
        __import__("joryu.mcp.http_bridge", fromlist=["_TOOL_HANDLERS"])._TOOL_HANDLERS,
        "weather",
        _timeout,
    )
    resp = bridge_client.post("/tools/weather", json={"location": "Tokyo"})
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]


def test_mcp_http_httpx_error_returns_502(
    bridge_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def _http_fail(_args: dict) -> str:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setitem(
        __import__("joryu.mcp.http_bridge", fromlist=["_TOOL_HANDLERS"])._TOOL_HANDLERS,
        "weather",
        _http_fail,
    )
    resp = bridge_client.post("/tools/weather", json={"location": "Tokyo"})
    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]
