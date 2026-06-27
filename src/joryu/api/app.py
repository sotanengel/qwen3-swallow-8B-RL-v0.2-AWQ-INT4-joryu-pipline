"""FastAPI アプリケーション。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from joryu.api.routes import chat, curate, dashboard, jobs, search, seed_gen
from joryu.chat.session import ChatSessionStore
from joryu.config import load_config
from joryu.http_client import close_shared_async_client
from joryu.jobs.runner import JobRunner, default_jobs_dir
from joryu.jobs.store import JobStore
from joryu.mcp_runtime import probe_mcp_health
from joryu.tools_impl.weather import apply_weather_config


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_shared_async_client()


def repo_root_from_env() -> Path:
    env = os.environ.get("JORYU_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def create_app(*, repo_root: Path | None = None) -> FastAPI:
    root = repo_root or repo_root_from_env()
    store = JobStore(default_jobs_dir(root))
    runner = JobRunner(store, root)
    runner.reconcile_stale_jobs()

    app = FastAPI(title="joryu API", version="0.1.0", lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.repo_root = root
    app.state.job_store = store
    app.state.job_runner = runner
    app.state.search_indexes = {}
    app.state.chat_sessions = ChatSessionStore(
        db_path=root / "data" / "chat" / "sessions.db",
    )

    cfg_path = root / "config.yaml"
    if cfg_path.exists():
        cfg = load_config(cfg_path)
        apply_weather_config(
            timeout=cfg.tools.weather.timeout,
            provider=cfg.tools.weather.provider,
        )
        app.state.mcp_runtime = probe_mcp_health(
            url=cfg.mcp.url,
            enabled=cfg.mcp.enabled,
        )
    else:
        from joryu.mcp_runtime import McpRuntimeState

        app.state.mcp_runtime = McpRuntimeState(enabled=False, state="down")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(curate.router, prefix="/api/curate/jobs", tags=["curate"])
    app.include_router(seed_gen.router, prefix="/api/seed-gen/jobs", tags=["seed_gen"])
    app.include_router(seed_gen.status_router, prefix="/api/seed-gen", tags=["seed_gen"])
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(search.router, prefix="/api/dashboard", tags=["dashboard"])
    return app
