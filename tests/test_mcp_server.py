"""MCP サーバーのテスト。"""

from __future__ import annotations

import pytest


def test_list_tool_names() -> None:
    from joryu.mcp import list_tool_names

    names = list_tool_names()
    assert names == ["today_jst", "web_search", "weather", "fetch_url"]


def test_create_mcp_server_registers_tools() -> None:
    pytest.importorskip("mcp")
    from joryu.mcp import create_mcp_server

    server = create_mcp_server()
    assert server.name == "joryu"
