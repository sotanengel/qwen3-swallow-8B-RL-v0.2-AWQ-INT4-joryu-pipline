"""McpToolExecutor のテスト。"""

from __future__ import annotations

import httpx
import pytest
import respx

from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import McpToolExecutor


def test_mcp_tool_executor_runs_weather_locally(monkeypatch) -> None:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    ex = McpToolExecutor()
    with pytest.raises(ValueError):
        ex.run(ParsedToolCall(name="weather", arguments={"location": ""}, raw=""))


@respx.mock
def test_mcp_tool_executor_remote_bridge() -> None:
    respx.post("http://localhost:8200/tools/weather").mock(
        return_value=httpx.Response(200, json={"result": "晴れ"})
    )
    ex = McpToolExecutor(url="http://localhost:8200")
    out = ex.run(
        ParsedToolCall(name="weather", arguments={"location": "東京"}, raw=""),
    )
    assert out == "晴れ"


def test_mcp_tool_executor_calc_stays_local() -> None:
    ex = McpToolExecutor()
    out = ex.run(ParsedToolCall(name="calc", arguments={"expression": "2+2"}, raw=""))
    assert out == "4"


@respx.mock
def test_mcp_tool_executor_uses_configurable_timeout() -> None:
    route = respx.post("http://localhost:8200/tools/weather").mock(
        side_effect=httpx.TimeoutException("timeout"),
    )
    ex = McpToolExecutor(
        url="http://localhost:8200",
        connect_timeout=0.1,
        read_timeout=0.1,
    )
    with pytest.raises(httpx.TimeoutException):
        ex.run(ParsedToolCall(name="weather", arguments={"location": "東京"}, raw=""))
    assert route.called
