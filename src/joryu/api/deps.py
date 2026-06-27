"""FastAPI 依存性注入。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from joryu.chat.session import ChatSessionStore
from joryu.config import load_config
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.tool_executor import McpToolExecutor, ToolExecutor, build_default_executor
from joryu.tools import load_tools, merge_tools
from joryu.vllm_client import (
    SupportsChat,
    SupportsChatStream,
    resolve_chat_client,
    resolve_stream_chat_client,
)


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_runner(request: Request) -> JobRunner:
    return request.app.state.job_runner


def get_session_store(request: Request) -> ChatSessionStore:
    return request.app.state.chat_sessions


RunnerDep = Annotated[JobRunner, Depends(get_runner)]


def require_idle(runner: RunnerDep) -> None:
    """ジョブ実行中は GPU 衝突回避のため 409 を返す。"""
    if runner.running_id is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "job_active", "running_id": runner.running_id},
        )


def _load_repo_config(request: Request) -> tuple[Path, Any]:
    repo_root = request.app.state.repo_root
    cfg = load_config(repo_root / "config.yaml")
    return repo_root, cfg


def get_chat_client(request: Request) -> SupportsChat:
    override = getattr(request.app.state, "chat_client", None)
    if override is not None:
        return override
    _repo_root, cfg = _load_repo_config(request)
    return resolve_chat_client(cfg.model, cfg.vllm)


def get_stream_chat_client(request: Request) -> SupportsChatStream | None:
    override = getattr(request.app.state, "stream_chat_client", None)
    if override is not None:
        return override
    if getattr(request.app.state, "chat_client", None) is not None:
        return None
    _repo_root, cfg = _load_repo_config(request)
    return resolve_stream_chat_client(cfg.model, cfg.vllm)


def get_executor(request: Request) -> ToolExecutor:
    override = getattr(request.app.state, "chat_executor", None)
    if override is not None:
        return override
    _repo_root, cfg = _load_repo_config(request)
    if cfg.mcp.enabled:
        return McpToolExecutor(url=cfg.mcp.url)
    return build_default_executor()


def get_session_context(
    request: Request,
) -> tuple[Path, Any, list[dict[str, Any]], list[str], Path]:
    repo_root, cfg = _load_repo_config(request)
    tools_map = load_tools(repo_root / cfg.distill.tools_file)
    tool_ids = sorted(tools_map.keys())
    tools_schema = merge_tools([t.to_openai_schema() for t in tools_map.values()], [])
    out_path = repo_root / cfg.distill.out_dir / cfg.distill.out_file
    return repo_root, cfg, tools_schema, tool_ids, out_path
