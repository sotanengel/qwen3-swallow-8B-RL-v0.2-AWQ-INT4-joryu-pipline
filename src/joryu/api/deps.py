"""FastAPI 依存性注入。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from joryu.chat.session import ChatSessionStore
from joryu.config import load_config
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.orchestrator.profile import ModelProfile
from joryu.orchestrator.service import ModelOrchestrator
from joryu.orchestrator.state import OrchestratorStatus
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


def get_orchestrator(request: Request) -> ModelOrchestrator:
    return request.app.state.orchestrator


def get_session_store(request: Request) -> ChatSessionStore:
    return request.app.state.chat_sessions


RunnerDep = Annotated[JobRunner, Depends(get_runner)]
OrchDep = Annotated[ModelOrchestrator, Depends(get_orchestrator)]


def require_idle(runner: RunnerDep) -> None:
    """ジョブ実行中は GPU 衝突回避のため 409 を返す。"""
    if runner.running_id is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "job_active", "running_id": runner.running_id},
        )


def require_chat_profile(orchestrator: OrchDep) -> None:
    """chat は distill profile が active なときのみ通す。"""
    state = orchestrator.get_state()
    if state.status != OrchestratorStatus.ACTIVE or state.active != ModelProfile.DISTILL:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "wrong_profile",
                "active": state.active.value if state.active else None,
                "required": ModelProfile.DISTILL.value,
                "status": state.status.value,
            },
        )


def assert_profile_enqueueable(orchestrator: ModelOrchestrator, required: ModelProfile) -> None:
    """ジョブ enqueue 前: profile 切替中でなければ OK (起動は JobRunner が担当)。"""
    state = orchestrator.get_state()
    if state.status == OrchestratorStatus.SWITCHING:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "profile_switching",
                "target": state.target.value if state.target else None,
            },
        )
    if state.status == OrchestratorStatus.STARTING and state.target != required:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "profile_starting",
                "target": state.target.value if state.target else None,
                "required": required.value,
            },
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
    mcp_runtime = getattr(request.app.state, "mcp_runtime", None)
    mcp_enabled = cfg.mcp.enabled
    if mcp_runtime is not None:
        mcp_enabled = mcp_runtime.enabled
    if mcp_enabled:
        return McpToolExecutor(
            url=cfg.mcp.url,
            connect_timeout=cfg.mcp.timeout.connect,
            read_timeout=cfg.mcp.timeout.read,
        )
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
