"""MCP 未到達時のローカルフォールバック (#205)。"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from joryu.api.app import create_app
from joryu.mcp_runtime import McpRuntimeState, probe_mcp_health
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import McpToolExecutor


@respx.mock
def test_mcp_executor_falls_back_on_connect_error(monkeypatch) -> None:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    respx.post("http://localhost:8200/tools/web_search").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    ex = McpToolExecutor(url="http://localhost:8200")
    out = ex.run(
        ParsedToolCall(name="search", arguments={"query": "東京 天気"}, raw=""),
    )
    assert "stub" in out


@respx.mock
def test_mcp_executor_falls_back_on_5xx(monkeypatch) -> None:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    respx.post("http://localhost:8200/tools/web_search").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"}),
    )
    ex = McpToolExecutor(url="http://localhost:8200")
    out = ex.run(
        ParsedToolCall(name="search", arguments={"query": "東京 天気"}, raw=""),
    )
    assert "stub" in out or "東京" in out


@respx.mock
def test_probe_mcp_health_downgrades_when_unreachable() -> None:
    respx.get("http://localhost:8200/health").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    state = probe_mcp_health(url="http://localhost:8200", enabled=True)
    assert state.enabled is False
    assert state.state == "down"


@respx.mock
def test_probe_mcp_health_keeps_enabled_when_ok() -> None:
    respx.get("http://localhost:8200/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )
    state = probe_mcp_health(url="http://localhost:8200", enabled=True)
    assert state.enabled is True
    assert state.state == "up"


def test_create_app_degrades_mcp_when_health_fails(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        """
mcp:
  enabled: true
  url: "http://localhost:8200"
tools:
  weather:
    timeout: 5.0
    provider: open_meteo
""".strip(),
        encoding="utf-8",
    )
    with respx.mock:
        respx.get("http://localhost:8200/health").mock(
            side_effect=httpx.ConnectError("connection refused"),
        )
        app = create_app(repo_root=tmp_path)
    runtime = app.state.mcp_runtime
    assert isinstance(runtime, McpRuntimeState)
    assert runtime.enabled is False
    assert runtime.state == "down"
