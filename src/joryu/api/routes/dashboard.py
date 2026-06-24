"""ダッシュボード向けライブデータ取得 API。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from joryu.paths import resolve_stats_output_path
from joryu.preflight import resolve_distill_jsonl
from joryu.stats import compute_stats

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _repo_root(request: Request) -> Path:
    return request.app.state.repo_root


@router.get("/stats")
def get_stats(request: Request) -> Response:
    """dashboard/public/stats.json をライブ読み込み (キャッシュ無効)。"""
    root = _repo_root(request)
    path = resolve_stats_output_path(repo_root=root)
    if path is None or not path.is_file():
        return JSONResponse(compute_stats(Path("__missing__")), headers=_NO_STORE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return JSONResponse(compute_stats(Path("__missing__")), headers=_NO_STORE)
    if not isinstance(data, dict):
        return JSONResponse(compute_stats(Path("__missing__")), headers=_NO_STORE)
    return JSONResponse(data, headers=_NO_STORE)


@router.get("/responses")
def get_responses(request: Request) -> Response:
    """蒸留 JSONL をライブ読み込み (キャッシュ無効)。"""
    root = _repo_root(request)
    jsonl = resolve_distill_jsonl(root)
    if not jsonl.is_file():
        return PlainTextResponse("", headers=_NO_STORE)
    try:
        text = jsonl.read_text(encoding="utf-8")
    except OSError:
        return PlainTextResponse("", headers=_NO_STORE)
    return PlainTextResponse(text, media_type="application/x-ndjson", headers=_NO_STORE)
