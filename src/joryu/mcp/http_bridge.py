"""MCP HTTP bridge — McpToolExecutor 向け REST エンドポイント。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from joryu.tools_impl.fetch import fetch_url as fetch_impl
from joryu.tools_impl.search import web_search as search_impl
from joryu.tools_impl.weather import fetch_weather as weather_impl


class ToolResult(BaseModel):
    result: str


def _run_weather(args: dict[str, Any]) -> str:
    location = str(args.get("location") or "")
    date = args.get("date")
    date_str = str(date) if date is not None else None
    return weather_impl(location, date_str)


def _run_web_search(args: dict[str, Any]) -> str:
    query = str(args.get("query") or "")
    top_k = int(args.get("top_k") or 5)
    return search_impl(query, top_k=top_k)


def _run_fetch_url(args: dict[str, Any]) -> str:
    url = str(args.get("url") or "")
    return fetch_impl(url)


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "weather": _run_weather,
    "web_search": _run_web_search,
    "fetch_url": _run_fetch_url,
}


def create_http_app() -> FastAPI:
    app = FastAPI(title="joryu-mcp-http")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/tools/{tool_name}", response_model=ToolResult)
    def run_tool(tool_name: str, body: dict[str, Any]) -> ToolResult:
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name!r}")
        try:
            return ToolResult(result=handler(body))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


def run_http_server(*, host: str = "127.0.0.1", port: int = 8200) -> None:
    import uvicorn

    uvicorn.run(create_http_app(), host=host, port=port, log_level="info")
