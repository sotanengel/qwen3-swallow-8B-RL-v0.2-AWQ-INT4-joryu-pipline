"""curation ジョブ API ルート。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from joryu.jobs.models import CurateJobSpec, JobKind, JobRecord
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.jobs.validate import validate_curate_job_spec
from joryu.paths import DEFAULT_CONFIG
from joryu.preflight import joryu_container_running, jsonl_has_content, resolve_distill_jsonl

router = APIRouter()

CurateRequestBody = Annotated[dict[str, Any], Body()]


class CurateJobResponse(BaseModel):
    id: str
    kind: str
    spec: dict[str, Any]
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    error: str | None = None

    @classmethod
    def from_record(cls, record: JobRecord) -> CurateJobResponse:
        return cls(
            id=record.id,
            kind=record.kind.value,
            spec=record.spec.to_dict(),
            status=record.status.value,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            exit_code=record.exit_code,
            error=record.error,
        )


class LogResponse(BaseModel):
    chunk: str
    offset: int


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


def _runner(request: Request) -> JobRunner:
    return request.app.state.job_runner


def _curate_jobs(store: JobStore) -> list[JobRecord]:
    return [r for r in store.list_all() if r.kind == JobKind.CURATE]


@router.get("/options")
def curate_options(request: Request) -> dict[str, Any]:
    repo_root = request.app.state.repo_root
    jsonl = resolve_distill_jsonl(repo_root)
    return {
        "defaults": {"config": DEFAULT_CONFIG, "skip_llm": False},
        "input_ready": jsonl_has_content(jsonl),
        "vllm_available": joryu_container_running(),
    }


@router.post("", response_model=CurateJobResponse, status_code=201)
def create_curate_job(
    request: Request,
    body: CurateRequestBody,
) -> CurateJobResponse:
    repo_root = request.app.state.repo_root
    spec = CurateJobSpec.from_dict(body)
    try:
        validate_curate_job_spec(spec, repo_root=repo_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not spec.skip_llm and not joryu_container_running():
        raise HTTPException(
            status_code=400,
            detail=(
                "vLLM (joryu コンテナ) が起動していません。"
                " `uv run joryu-up --full` で joryu を起動するか、"
                "skip_llm=true を指定してください。"
            ),
        )

    record = JobRecord.create(spec)
    _store(request).save(record)
    _runner(request).enqueue(record)
    return CurateJobResponse.from_record(record)


@router.get("", response_model=list[CurateJobResponse])
def list_curate_jobs(request: Request) -> list[CurateJobResponse]:
    records = _curate_jobs(_store(request))
    return [CurateJobResponse.from_record(r) for r in records]


@router.get("/{job_id}", response_model=CurateJobResponse)
def get_curate_job(job_id: str, request: Request) -> CurateJobResponse:
    try:
        record = _store(request).load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.CURATE:
        raise HTTPException(status_code=404, detail="job not found")
    return CurateJobResponse.from_record(record)


@router.get("/{job_id}/logs", response_model=LogResponse)
def get_curate_job_logs(job_id: str, request: Request, offset: int = 0) -> LogResponse:
    store = _store(request)
    try:
        record = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.CURATE:
        raise HTTPException(status_code=404, detail="job not found")
    chunk, new_offset = store.read_log(job_id, offset=offset)
    return LogResponse(chunk=chunk, offset=new_offset)


@router.post("/{job_id}/cancel", response_model=CurateJobResponse)
def cancel_curate_job(job_id: str, request: Request) -> CurateJobResponse:
    store = _store(request)
    try:
        record = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.CURATE:
        raise HTTPException(status_code=404, detail="job not found")
    _runner(request).cancel(job_id)
    return CurateJobResponse.from_record(store.load(job_id))
