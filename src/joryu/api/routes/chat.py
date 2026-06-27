"""インタラクティブチャット API ルート。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from joryu.api.deps import (
    get_chat_client,
    get_executor,
    get_session_store,
    get_stream_chat_client,
    require_idle,
)
from joryu.chat.service import ChatService
from joryu.chat.session import ChatSession, ChatSessionStore
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import SupportsChat, SupportsChatStream

router = APIRouter()


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


def _chat_service(
    request: Request,
    chat_client: Annotated[SupportsChat, Depends(get_chat_client)],
    stream_client: Annotated[SupportsChatStream | None, Depends(get_stream_chat_client)],
    executor: Annotated[ToolExecutor, Depends(get_executor)],
    session_store: Annotated[ChatSessionStore, Depends(get_session_store)],
) -> ChatService:
    return ChatService(
        repo_root=request.app.state.repo_root,
        session_store=session_store,
        chat_client=chat_client,
        executor=executor,
        stream_client=stream_client,
    )


ChatServiceDep = Annotated[ChatService, Depends(_chat_service)]


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


@router.get("/styles", response_model=list[StyleItem])
def list_styles(service: ChatServiceDep) -> list[StyleItem]:
    styles = service.load_styles()
    return [
        StyleItem(style_id=preset.style_id, label=preset.label)
        for preset in sorted(styles.values(), key=lambda p: p.style_id)
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(service: ChatServiceDep) -> SessionResponse:
    styles = service.load_styles()
    session = service.create_session(styles)
    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, service: ChatServiceDep) -> SessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_to_response(session)


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
def delete_session(session_id: str, service: ChatServiceDep) -> Response:
    if not service.delete_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


@router.post(
    "/sessions/{session_id}/messages",
    dependencies=[Depends(require_idle)],
)
def post_all_messages(
    session_id: str,
    body: MessageRequest,
    request: Request,
    service: ChatServiceDep,
) -> StreamingResponse:
    """初回専用: 全列に同一 prompt を並列 SSE 配信。"""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not all(col.turn_index == 0 for col in session.columns.values()):
        raise HTTPException(
            status_code=400,
            detail="initial broadcast requires all columns at turn_index 0",
        )
    return StreamingResponse(
        service.stream_all_columns(session, body.prompt, request=request),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/sessions/{session_id}/columns/{style_id}/messages",
    dependencies=[Depends(require_idle)],
)
def post_column_message(
    session_id: str,
    style_id: str,
    body: MessageRequest,
    request: Request,
    service: ChatServiceDep,
) -> StreamingResponse:
    """2 ターン目以降: 指定列のみ SSE 配信。"""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if style_id not in session.columns:
        raise HTTPException(status_code=404, detail="column not found")
    return StreamingResponse(
        service.stream_single_column(session, style_id, body.prompt, request=request),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/sessions/{session_id}/_probe",
    dependencies=[Depends(require_idle)],
)
def probe_idle(session_id: str, service: ChatServiceDep) -> dict[str, str]:
    """409 ガード確認用。"""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "idle_ok"}
