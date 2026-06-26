"""インタラクティブチャット API ルート。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from joryu.chat.session import ChatSession, ChatSessionStore
from joryu.chat.streamer import stream_column_turn
from joryu.config import load_config
from joryu.jobs.models import JobStatus
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.styles import load_styles
from joryu.tool_executor import ToolExecutor, build_default_executor
from joryu.tools import load_tools, merge_tools
from joryu.vllm_client import SupportsChat, resolve_chat_client

router = APIRouter()

DEFAULT_SAMPLING = {"temperature": 0.7, "top_p": 0.9}


class StyleItem(BaseModel):
    style_id: str
    label: str


class ColumnResponse(BaseModel):
    style_id: str
    label: str
    messages: list[dict[str, Any]]
    turn_index: int


class SessionResponse(BaseModel):
    session_id: str
    columns: list[ColumnResponse]


class MessageRequest(BaseModel):
    prompt: str = Field(min_length=1)


def _sessions(request: Request) -> ChatSessionStore:
    return request.app.state.chat_sessions


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


def _runner(request: Request) -> JobRunner:
    return request.app.state.job_runner


def _require_idle(request: Request) -> None:
    """ジョブ実行中は GPU 衝突回避のため 409 を返す。"""
    runner = _runner(request)
    store = _store(request)
    running_id = runner.running_id
    if running_id is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "job_active", "running_id": running_id},
        )
    for job in store.list_all():
        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise HTTPException(
                status_code=409,
                detail={"error": "job_active", "running_id": running_id},
            )


def _session_to_response(session: ChatSession) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        columns=[
            ColumnResponse(
                style_id=col.style_id,
                label=col.label,
                messages=list(col.messages),
                turn_index=col.turn_index,
            )
            for col in session.columns.values()
        ],
    )


def _load_repo_config(request: Request):
    repo_root = request.app.state.repo_root
    cfg = load_config(repo_root / "config.yaml")
    return repo_root, cfg


def _load_styles_for_repo(request: Request):
    repo_root, cfg = _load_repo_config(request)
    styles_path = repo_root / cfg.distill.styles_file
    return load_styles(styles_path)


def _resolve_chat_client(request: Request) -> SupportsChat:
    override = getattr(request.app.state, "chat_client", None)
    if override is not None:
        return override
    repo_root, cfg = _load_repo_config(request)
    return resolve_chat_client(cfg.model, cfg.vllm)


def _resolve_executor(request: Request) -> ToolExecutor:
    override = getattr(request.app.state, "chat_executor", None)
    if override is not None:
        return override
    return build_default_executor()


def _session_context(request: Request) -> tuple[Path, Any, list[dict[str, Any]], list[str], Path]:
    repo_root, cfg = _load_repo_config(request)
    tools_map = load_tools(repo_root / cfg.distill.tools_file)
    tool_ids = sorted(tools_map.keys())
    tools_schema = merge_tools([t.to_openai_schema() for t in tools_map.values()], [])
    out_path = repo_root / cfg.distill.out_dir / cfg.distill.out_file
    return repo_root, cfg, tools_schema, tool_ids, out_path


def _format_sse(event: dict[str, Any]) -> str:
    event_type = event.pop("type")
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _merge_streams(
    streams: list[tuple[str, AsyncIterator[dict[str, Any]]]],
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    total = len(streams)

    async def pump(column_id: str, stream: AsyncIterator[dict[str, Any]]) -> None:
        try:
            async for event in stream:
                await queue.put(event)
        except Exception as exc:
            await queue.put(
                {"type": "error", "column": column_id, "message": str(exc)},
            )
        finally:
            await queue.put(None)

    tasks = [asyncio.create_task(pump(cid, s)) for cid, s in streams]
    done = 0
    while done < total:
        item = await queue.get()
        if item is None:
            done += 1
        else:
            yield item
    await asyncio.gather(*tasks, return_exceptions=True)


async def _sse_all_columns(
    request: Request,
    session: ChatSession,
    prompt: str,
) -> AsyncIterator[str]:
    client = _resolve_chat_client(request)
    streams = [
        (
            col.style_id,
            stream_column_turn(
                session,
                col,
                prompt,
                client=client,
                sampling=DEFAULT_SAMPLING,
            ),
        )
        for col in session.columns.values()
    ]
    async for event in _merge_streams(streams):
        yield _format_sse(dict(event))
    yield _format_sse({"type": "done", "session_id": session.session_id})


async def _sse_single_column(
    request: Request,
    session: ChatSession,
    style_id: str,
    prompt: str,
) -> AsyncIterator[str]:
    if style_id not in session.columns:
        yield _format_sse({"type": "error", "message": f"unknown column: {style_id}"})
        return
    client = _resolve_chat_client(request)
    column = session.columns[style_id]
    async for event in stream_column_turn(
        session,
        column,
        prompt,
        client=client,
        sampling=DEFAULT_SAMPLING,
    ):
        yield _format_sse(dict(event))
    yield _format_sse({"type": "done", "session_id": session.session_id})


@router.get("/styles", response_model=list[StyleItem])
def list_styles(request: Request) -> list[StyleItem]:
    styles = _load_styles_for_repo(request)
    return [
        StyleItem(style_id=preset.style_id, label=preset.label)
        for preset in sorted(styles.values(), key=lambda p: p.style_id)
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(request: Request) -> SessionResponse:
    styles = _load_styles_for_repo(request)
    _repo_root, cfg, tools_schema, tool_ids, out_path = _session_context(request)
    session = _sessions(request).create(
        styles,
        base_system_prompt=cfg.distill.system_prompt,
        model_name=cfg.model.name,
        config_hash=cfg.fingerprint(),
        tools=tools_schema,
        tool_ids=tool_ids,
        out_path=out_path,
        executor=_resolve_executor(request),
    )
    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(request: Request, session_id: str) -> SessionResponse:
    session = _sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_to_response(session)


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
def delete_session(request: Request, session_id: str) -> Response:
    if not _sessions(request).delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@router.post("/sessions/{session_id}/messages")
def post_all_messages(
    request: Request,
    session_id: str,
    body: MessageRequest,
) -> StreamingResponse:
    """初回専用: 全列に同一 prompt を並列 SSE 配信。"""
    _require_idle(request)
    session = _sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not all(col.turn_index == 0 for col in session.columns.values()):
        raise HTTPException(
            status_code=400,
            detail="initial broadcast requires all columns at turn_index 0",
        )
    return StreamingResponse(
        _sse_all_columns(request, session, body.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/columns/{style_id}/messages")
def post_column_message(
    request: Request,
    session_id: str,
    style_id: str,
    body: MessageRequest,
) -> StreamingResponse:
    """2 ターン目以降: 指定列のみ SSE 配信。"""
    _require_idle(request)
    session = _sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if style_id not in session.columns:
        raise HTTPException(status_code=404, detail="column not found")
    return StreamingResponse(
        _sse_single_column(request, session, style_id, body.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/_probe")
def probe_idle(request: Request, session_id: str) -> dict[str, str]:
    """409 ガード確認用。"""
    _require_idle(request)
    session = _sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "idle_ok"}
