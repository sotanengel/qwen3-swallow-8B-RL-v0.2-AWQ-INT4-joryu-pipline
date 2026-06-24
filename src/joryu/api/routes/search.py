"""ダッシュボード BM25 検索 API。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from joryu.config import SearchConfig, load_config
from joryu.preflight import resolve_distill_jsonl
from joryu.search.index import SearchIndex

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _repo_root(request: Request) -> Path:
    return request.app.state.repo_root


def _load_search_config(repo_root: Path) -> SearchConfig:
    cfg_path = repo_root / "config.yaml"
    if cfg_path.is_file():
        try:
            return load_config(cfg_path).search
        except (OSError, ValueError) as exc:
            logger.warning("[search] config load failed: %s", exc)
    return SearchConfig()


def _get_index(request: Request) -> SearchIndex:
    cache: dict[str, SearchIndex] = request.app.state.search_indexes
    root = _repo_root(request)
    search_cfg = _load_search_config(root)
    key = str((root / search_cfg.index_dir).resolve())
    if key not in cache:
        cache[key] = SearchIndex(
            (root / search_cfg.index_dir).resolve(),
            snippet_chars=search_cfg.snippet_chars,
        )
    return cache[key]


def _ensure_index(request: Request) -> SearchIndex:
    root = _repo_root(request)
    jsonl = resolve_distill_jsonl(root)
    idx = _get_index(request)
    try:
        idx.ensure_fresh(jsonl)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return idx


class SearchRequest(BaseModel):
    query: str = ""
    mode: Literal["all", "thinking", "nothinking"] = "all"
    category: str = ""
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


@router.get("/search/status")
def search_status(request: Request) -> JSONResponse:
    root = _repo_root(request)
    jsonl = resolve_distill_jsonl(root)
    try:
        idx = _get_index(request)
    except Exception:
        idx = SearchIndex((root / _load_search_config(root).index_dir).resolve())
    info = idx.status_for(jsonl)
    return JSONResponse(
        {
            "index_status": info.index_status,
            "record_count": info.record_count,
            "built_at": info.built_at,
            "stale": info.stale,
        },
        headers=_NO_STORE,
    )


@router.post("/search")
def search_records(request: Request, body: SearchRequest) -> JSONResponse:
    try:
        idx = _ensure_index(request)
    except HTTPException:
        return JSONResponse(
            {
                "total": 0,
                "index_status": "unavailable",
                "hits": [],
            },
            status_code=503,
            headers=_NO_STORE,
        )

    category = body.category.strip() or None
    result = idx.search(
        body.query,
        mode=body.mode,
        category=category,
        limit=body.limit,
        offset=body.offset,
    )
    return JSONResponse(
        {
            "total": result.total,
            "index_status": result.index_status,
            "hits": [
                {
                    "record_key": h.record_key,
                    "score": h.score,
                    "snippet": h.snippet,
                    "snippet_field": h.snippet_field,
                    "record": h.record,
                }
                for h in result.hits
            ],
        },
        headers=_NO_STORE,
    )
