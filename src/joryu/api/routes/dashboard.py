"""ダッシュボード向けライブデータ取得 API。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from joryu.paths import resolve_stats_output_path
from joryu.preflight import ensure_stats_json, resolve_distill_jsonl
from joryu.responses_store import delete_all_records, delete_record
from joryu.stats import compute_stats

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _repo_root(request: Request) -> Path:
    return request.app.state.repo_root


def _refresh_stats(root: Path) -> None:
    ensure_stats_json(root, force=True)


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


@router.delete("/responses/{record_id}")
def delete_one_response(record_id: str, request: Request) -> JSONResponse:
    """指定 ID の出力レコードを 1 件削除する。"""
    root = _repo_root(request)
    jsonl = resolve_distill_jsonl(root)
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    if not jsonl.is_file():
        jsonl.touch()
    try:
        remaining = delete_record(jsonl, record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}") from exc
    _refresh_stats(root)
    return JSONResponse({"deleted": 1, "remaining": remaining}, headers=_NO_STORE)


@router.delete("/responses")
def delete_all_responses(request: Request) -> JSONResponse:
    """出力 JSONL を全件削除する。"""
    root = _repo_root(request)
    jsonl = resolve_distill_jsonl(root)
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    if not jsonl.is_file():
        jsonl.touch()
    deleted = delete_all_records(jsonl)
    _refresh_stats(root)
    return JSONResponse({"deleted": deleted, "remaining": 0}, headers=_NO_STORE)
