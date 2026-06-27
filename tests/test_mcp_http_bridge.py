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


def test_mcp_bridge_health_ok(bridge_client: TestClient) -> None:
    """#272: mcp_bridge 命名規則エイリアス。"""
    test_mcp_http_health(bridge_client)


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
    def _timeout(_location: str, _date: str | None = None) -> str:
        raise TimeoutError("upstream timed out")

    monkeypatch.setattr("joryu.mcp.http_bridge.weather_impl", _timeout)
    resp = bridge_client.post("/tools/weather", json={"location": "Tokyo"})
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]


def test_mcp_http_httpx_error_returns_502(
    bridge_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def _http_fail(_location: str, _date: str | None = None) -> str:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("joryu.mcp.http_bridge.weather_impl", _http_fail)
    resp = bridge_client.post("/tools/weather", json={"location": "Tokyo"})
    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]


def test_mcp_http_invalid_body_returns_422(bridge_client: TestClient) -> None:
    resp = bridge_client.post("/tools/web_search", json={"top_k": "not-a-number"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("missing") == []
    assert "errors" in detail


def test_mcp_http_empty_weather_location_returns_400(bridge_client: TestClient) -> None:
    resp = bridge_client.post("/tools/weather", json={"location": ""})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["missing"] == ["location"]
    assert "location" in detail["hint"]


def test_mcp_bridge_unknown_tool_returns_404(bridge_client: TestClient) -> None:
    resp = bridge_client.post("/tools/nope", json={})
    assert resp.status_code == 404


def test_mcp_bridge_value_error_returns_400(
    bridge_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _bad_fetch(_args) -> str:
        raise ValueError("invalid url")

    monkeypatch.setattr("joryu.mcp.http_bridge.fetch_impl", _bad_fetch)
    resp = bridge_client.post("/tools/fetch_url", json={"url": "not-a-url"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert "invalid url" in detail["hint"]
