"""vLLM 常駐デーモン HTTP サーバー (FastAPI)。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from joryu.vllm_client import ChatResult, SupportsChat


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    enable_thinking: bool | None = True
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | str | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)


def chat_result_to_dict(result: ChatResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["tool_calls"] = [
        {"name": tc.name, "arguments": tc.arguments} for tc in result.tool_calls
    ]
    payload["suspected_unparsed_tool_calls"] = list(result.suspected_unparsed_tool_calls)
    payload["raw_completion"] = result.raw_completion
    return payload


def warmup_client(client: SupportsChat) -> None:
    """モデルロード + 1 回推論で ready 状態にする。"""
    client.chat_via_template(
        [{"role": "user", "content": "こんにちは"}],
        enable_thinking=False,
        max_tokens=8,
        temperature=0.0,
    )


def create_llm_app(
    client: SupportsChat,
    *,
    model_loaded: bool = True,
) -> FastAPI:
    """LLM デーモン FastAPI アプリを構築する。"""
    app = FastAPI(title="joryu-llm-serve")
    app.state.model_loaded = model_loaded
    app.state.client = client

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        if not request.app.state.model_loaded:
            raise HTTPException(
                status_code=503,
                detail={"status": "loading", "model_loaded": False},
            )
        return {"status": "ok", "model_loaded": True}

    @app.post("/v1/chat")
    def chat(body: ChatRequest, request: Request) -> dict[str, Any]:
        if not request.app.state.model_loaded:
            raise HTTPException(status_code=503, detail="model not loaded")
        bound: SupportsChat = request.app.state.client
        result = bound.chat_via_template(
            body.messages,
            enable_thinking=body.enable_thinking,
            tools=body.tools,
            tool_choice=body.tool_choice,
            **body.sampling,
        )
        return chat_result_to_dict(result)

    return app
