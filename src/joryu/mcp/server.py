"""MCP サーバー実装。"""

from __future__ import annotations


def create_mcp_server():
    from mcp.server.fastmcp import FastMCP

    from joryu.datetime_context import format_date_context_ja, now_jst
    from joryu.tools_impl.fetch import fetch_url as fetch_impl
    from joryu.tools_impl.search import web_search as search_impl
    from joryu.tools_impl.weather import fetch_weather as weather_impl

    mcp = FastMCP("joryu")

    @mcp.tool()
    def today_jst() -> str:
        """Asia/Tokyo の今日の日付コンテキストを返す。"""
        return format_date_context_ja(now_jst())

    @mcp.tool()
    def web_search(query: str, top_k: int = 5) -> str:
        """Web 検索 (Tavily / stub)。"""
        return search_impl(query, top_k=top_k)

    @mcp.tool()
    def weather(location: str, date: str | None = None) -> str:
        """指定地点の天気 (Open-Meteo)。"""
        return weather_impl(location, date)

    @mcp.tool()
    def fetch_url(url: str) -> str:
        """URL 本文取得 (SSRF 対策付き)。"""
        return fetch_impl(url)

    return mcp


def list_tool_names() -> list[str]:
    return ["today_jst", "web_search", "weather", "fetch_url"]
