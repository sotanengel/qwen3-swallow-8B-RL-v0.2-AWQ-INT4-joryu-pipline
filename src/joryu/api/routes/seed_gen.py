"""seed-gen ジョブ API ルート。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from joryu.api.deps import assert_profile_enqueueable, get_orchestrator
from joryu.jobs.models import JobKind, JobRecord, JobStatus, SeedGenJobSpec
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.jobs.validate import validate_seed_gen_job_spec
from joryu.orchestrator.profile import ModelProfile
from joryu.orchestrator.required import required_profile_from_spec
from joryu.prompt_bank import load_prompt_bank
from joryu.prompt_dedup import ExactDedup
from joryu.seed_gen.config import DEFAULT_DOMAINS_REL, SeedGenConfig, resolve_domains_config_path
from joryu.seed_gen.counts import count_by_domain
from joryu.seed_gen.pipeline import DEFAULT_BANK_REL
from joryu.seed_gen.writer import DEFAULT_STATE_REL, atomic_append_jsonl, load_state, make_seed_row

router = APIRouter()
SeedGenRequestBody = Annotated[dict[str, Any], Body()]
ManualPromptBody = Annotated[dict[str, Any], Body()]


class SeedGenJobResponse(BaseModel):
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
    def from_record(cls, record: JobRecord) -> SeedGenJobResponse:
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


class DomainProgress(BaseModel):
    key: str
    target: int
    current: int
    ratio: float


class SeedGenStatusResponse(BaseModel):
    bank_total: int
    target_total: int
    domains: list[DomainProgress]
    state_updated_at: str | None = None
    running_job_ids: list[str] = Field(default_factory=list)


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


def _runner(request: Request) -> JobRunner:
    return request.app.state.job_runner


def _seed_gen_jobs(store: JobStore) -> list[JobRecord]:
    return [r for r in store.list_all() if r.kind == JobKind.SEED_GEN]


def _resolve_bank(repo_root: Any) -> Any:
    from pathlib import Path

    return Path(repo_root) / DEFAULT_BANK_REL


def _resolve_domains(repo_root: Any) -> SeedGenConfig:
    path = resolve_domains_config_path(repo_root, DEFAULT_DOMAINS_REL)
    return SeedGenConfig.load(path)


@router.get("/options")
def seed_gen_options(request: Request) -> dict[str, Any]:
    orchestrator = get_orchestrator(request)
    seed_ready = orchestrator.profile_ready(ModelProfile.SEED_GEN)
    screening_ready = orchestrator.profile_ready(ModelProfile.SCREENING)
    return {
        "defaults": {
            "bank": DEFAULT_BANK_REL,
            "domains_config": DEFAULT_DOMAINS_REL,
            "target_total": 230000,
        },
        "vllm_available": seed_ready,
        "seed_gen_ready": seed_ready,
        "screening_ready": screening_ready,
    }


def _build_status(request: Request) -> SeedGenStatusResponse:
    repo_root = request.app.state.repo_root
    cfg = _resolve_domains(repo_root)
    bank = _resolve_bank(repo_root)
    rows = load_prompt_bank(bank) if bank.is_file() else []
    counts = count_by_domain(rows, cfg)
    state = load_state(repo_root / DEFAULT_STATE_REL)
    running = [
        r.id
        for r in _seed_gen_jobs(_store(request))
        if r.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    ]
    domains = []
    for d in cfg.domains:
        current = counts.get(d.key, 0)
        ratio = current / d.target if d.target else 0.0
        domains.append(
            DomainProgress(key=d.key, target=d.target, current=current, ratio=round(ratio, 4))
        )
    return SeedGenStatusResponse(
        bank_total=len(rows),
        target_total=cfg.target_total,
        domains=domains,
        state_updated_at=state.updated_at or None,
        running_job_ids=running,
    )


@router.post("", response_model=SeedGenJobResponse, status_code=201)
def create_seed_gen_job(request: Request, body: SeedGenRequestBody) -> SeedGenJobResponse:
    repo_root = request.app.state.repo_root
    try:
        spec = SeedGenJobSpec.from_dict(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        validate_seed_gen_job_spec(spec, repo_root=repo_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    assert_profile_enqueueable(
        get_orchestrator(request),
        required_profile_from_spec(JobKind.SEED_GEN, spec),
    )

    record = JobRecord.create(spec, kind=JobKind.SEED_GEN)
    _store(request).save(record)
    _runner(request).enqueue(record)
    return SeedGenJobResponse.from_record(record)


@router.get("", response_model=list[SeedGenJobResponse])
def list_seed_gen_jobs(request: Request) -> list[SeedGenJobResponse]:
    return [SeedGenJobResponse.from_record(r) for r in _seed_gen_jobs(_store(request))]


@router.get("/{job_id}", response_model=SeedGenJobResponse)
def get_seed_gen_job(job_id: str, request: Request) -> SeedGenJobResponse:
    try:
        record = _store(request).load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.SEED_GEN:
        raise HTTPException(status_code=404, detail="job not found")
    return SeedGenJobResponse.from_record(record)


@router.get("/{job_id}/logs", response_model=LogResponse)
def get_seed_gen_job_logs(job_id: str, request: Request, offset: int = 0) -> LogResponse:
    store = _store(request)
    try:
        record = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.SEED_GEN:
        raise HTTPException(status_code=404, detail="job not found")
    chunk, new_offset = store.read_log(job_id, offset=offset)
    return LogResponse(chunk=chunk, offset=new_offset)


@router.post("/{job_id}/cancel", response_model=SeedGenJobResponse)
def cancel_seed_gen_job(job_id: str, request: Request) -> SeedGenJobResponse:
    store = _store(request)
    try:
        record = store.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if record.kind != JobKind.SEED_GEN:
        raise HTTPException(status_code=404, detail="job not found")
    _runner(request).cancel(job_id)
    return SeedGenJobResponse.from_record(store.load(job_id))


status_router = APIRouter()


@status_router.post("/prompts")
def append_manual_prompt(request: Request, body: ManualPromptBody) -> dict[str, Any]:
    """手動 1 件追記 (Stage1 重複チェックのみ)。"""
    prompt = str(body.get("prompt") or "").strip()
    domain = str(body.get("domain") or "").strip()
    if not prompt or not domain:
        raise HTTPException(status_code=400, detail="prompt and domain are required")
    repo_root = request.app.state.repo_root
    cfg = _resolve_domains(repo_root)
    if domain not in {d.key for d in cfg.domains}:
        raise HTTPException(status_code=400, detail=f"unknown domain: {domain}")
    bank = _resolve_bank(repo_root)
    dedup = ExactDedup()
    if bank.is_file():
        dedup.seed_from_existing(r.prompt for r in load_prompt_bank(bank))
    if dedup.is_duplicate(prompt):
        raise HTTPException(status_code=409, detail="duplicate prompt (stage1)")
    row = make_seed_row(prompt, domain)
    atomic_append_jsonl(bank, [row])
    return {"id": row["id"], "domain": domain}


@status_router.get("/status", response_model=SeedGenStatusResponse)
def seed_gen_status(request: Request) -> SeedGenStatusResponse:
    return _build_status(request)
