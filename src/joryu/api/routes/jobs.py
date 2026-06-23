"""ジョブ API ルート。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from joryu.config import load_config
from joryu.jobs.models import DistillJobSpec, JobRecord
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.jobs.validate import validate_job_spec
from joryu.paths import DEFAULT_CONFIG
from joryu.styles import load_styles

router = APIRouter()

JobRequestBody = Annotated[dict[str, Any], Body()]


class JobResponse(BaseModel):
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
    def from_record(cls, record: JobRecord) -> JobResponse:
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


@router.get("/options")
def job_options(request: Request) -> dict[str, Any]:
    repo_root = request.app.state.repo_root
    cfg = load_config(repo_root / "config.yaml")
    styles_path = repo_root / cfg.distill.styles_file
    styles = load_styles(styles_path)
    return {
        "modes": ["thinking", "nothinking"],
        "styles": [{"id": sid, "label": preset.label} for sid, preset in sorted(styles.items())],
        "defaults": {
            "config": DEFAULT_CONFIG,
            "mode": cfg.model.mode,
        },
    }


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    request: Request,
    body: JobRequestBody,
) -> JobResponse:
    repo_root = request.app.state.repo_root
    spec = DistillJobSpec.from_dict(body)
    try:
        validate_job_spec(spec, repo_root=repo_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = JobRecord.create(spec)
    _store(request).save(record)
    _runner(request).enqueue(record)
    return JobResponse.from_record(record)


@router.get("", response_model=list[JobResponse])
def list_jobs(request: Request) -> list[JobResponse]:
    records = _store(request).list_all()
    return [JobResponse.from_record(r) for r in records]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request) -> JobResponse:
    try:
        record = _store(request).load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return JobResponse.from_record(record)


@router.get("/{job_id}/logs", response_model=LogResponse)
def get_job_logs(job_id: str, request: Request, offset: int = 0) -> LogResponse:
    store = _store(request)
    try:
        store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    chunk, new_offset = store.read_log(job_id, offset=offset)
    return LogResponse(chunk=chunk, offset=new_offset)


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, request: Request) -> JobResponse:
    store = _store(request)
    try:
        store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    _runner(request).cancel(job_id)
    return JobResponse.from_record(store.load(job_id))
