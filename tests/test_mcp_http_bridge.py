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
