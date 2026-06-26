"""インタラクティブチャット API ルート。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from joryu.chat.session import ChatSessionStore
from joryu.config import load_config
from joryu.jobs.models import JobStatus
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.styles import load_styles

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


def _session_to_response(session: Any) -> SessionResponse:
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


def _load_styles_for_repo(request: Request) -> dict[str, Any]:
    repo_root = request.app.state.repo_root
    cfg = load_config(repo_root / "config.yaml")
    styles_path = repo_root / cfg.distill.styles_file
    return load_styles(styles_path)


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
    session = _sessions(request).create(styles)
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


@router.post("/sessions/{session_id}/_probe")
def probe_idle(request: Request, session_id: str) -> dict[str, str]:
    """409 ガード確認用スタブ（#149 で本番送信 endpoint に適用）。"""
    _require_idle(request)
    session = _sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "idle_ok"}
