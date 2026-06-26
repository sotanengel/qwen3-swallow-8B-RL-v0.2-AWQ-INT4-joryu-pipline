"""FastAPI アプリケーション。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from joryu.api.routes import chat, curate, dashboard, jobs, search
from joryu.chat.session import ChatSessionStore
from joryu.jobs.runner import JobRunner, default_jobs_dir
from joryu.jobs.store import JobStore


def repo_root_from_env() -> Path:
    env = os.environ.get("JORYU_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def create_app(*, repo_root: Path | None = None) -> FastAPI:
    root = repo_root or repo_root_from_env()
    store = JobStore(default_jobs_dir(root))
    runner = JobRunner(store, root)

    app = FastAPI(title="joryu API", version="0.1.0")
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
    app.state.chat_sessions = ChatSessionStore()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(curate.router, prefix="/api/curate/jobs", tags=["curate"])
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(search.router, prefix="/api/dashboard", tags=["dashboard"])
    return app
