"""システム状態 API (ModelProfile FSM)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from joryu.orchestrator.service import ModelOrchestrator
from joryu.paths import SCREENING_JSON_REL

router = APIRouter()
live_router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _orchestrator(request: Request) -> ModelOrchestrator:
    return request.app.state.orchestrator


def models_snapshot(orchestrator: ModelOrchestrator) -> dict[str, Any]:
    state = orchestrator.get_state()
    profiles: list[dict[str, Any]] = []
    for profile, spec in orchestrator.profiles.items():
        profiles.append(
            {
                "name": profile.value,
                "ready": orchestrator.profile_ready(profile),
                "port": spec.port,
                "service": spec.service,
                "kind": spec.kind,
            }
        )
    return {
        **state.to_dict(),
        "profiles": profiles,
    }


@router.get("/models")
def get_models(request: Request) -> JSONResponse:
    return JSONResponse(models_snapshot(_orchestrator(request)), headers=_NO_STORE)


@router.get("/models/stream")
def stream_models(request: Request) -> StreamingResponse:
    orchestrator = _orchestrator(request)

    def event_stream():
        for _state in orchestrator.subscribe():
            payload = json.dumps(models_snapshot(orchestrator), ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_NO_STORE)


@live_router.get("/screening")
def live_screening(request: Request) -> JSONResponse:
    root: Path = request.app.state.repo_root
    path = root / SCREENING_JSON_REL
    if not path.is_file():
        raise HTTPException(status_code=404, detail="screening.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="failed to read screening.json") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="invalid screening.json")
    return JSONResponse(data, headers=_NO_STORE)
