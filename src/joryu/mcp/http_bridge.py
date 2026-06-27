"""MCP HTTP bridge — McpToolExecutor 向け REST エンドポイント。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from joryu.tools_impl.fetch import fetch_url as fetch_impl
from joryu.tools_impl.search import web_search as search_impl
from joryu.tools_impl.weather import fetch_weather as weather_impl


class HealthResponse(BaseModel):
    status: str = "ok"


class ToolResult(BaseModel):
    result: str


class WeatherArgs(BaseModel):
    location: str = ""
    date: str | None = None


class WebSearchArgs(BaseModel):
    query: str = ""
    top_k: int = Field(default=5, ge=1, le=50)


class FetchUrlArgs(BaseModel):
    url: str = ""


def _run_weather(args: WeatherArgs) -> str:
    return weather_impl(args.location, args.date)


def _run_web_search(args: WebSearchArgs) -> str:
    return search_impl(args.query, top_k=args.top_k)


def _run_fetch_url(args: FetchUrlArgs) -> str:
    return fetch_impl(args.url)


_TOOL_SPECS: dict[str, tuple[type[BaseModel], Callable[[Any], str]]] = {
    "weather": (WeatherArgs, _run_weather),
    "web_search": (WebSearchArgs, _run_web_search),
    "fetch_url": (FetchUrlArgs, _run_fetch_url),
}


def create_http_app() -> FastAPI:
    app = FastAPI(title="joryu-mcp-http")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/tools/{tool_name}", response_model=ToolResult)
    def run_tool(tool_name: str, body: dict[str, Any]) -> ToolResult:
        spec = _TOOL_SPECS.get(tool_name)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name!r}")
        model_cls, handler = spec
        try:
            args = model_cls.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        try:
            return ToolResult(result=handler(args))
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
