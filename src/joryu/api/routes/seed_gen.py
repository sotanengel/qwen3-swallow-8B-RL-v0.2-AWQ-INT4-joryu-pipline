"""seed-gen ジョブ API ルート。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from joryu.api.deps import get_orchestrator
from joryu.core.prompt_bank import load_prompt_bank
from joryu.jobs.models import JobKind, JobRecord, JobStatus, SeedGenJobSpec
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from joryu.jobs.validate import validate_seed_gen_job_spec
from joryu.orchestrator.profile import ModelProfile
from joryu.persistence.prompt_dedup import ExactDedup
from joryu.seed_gen.check_state import (
    compute_check_status,
    mark_all_unchecked,
    mark_checked,
    prompt_check_key,
)
from joryu.seed_gen.config import DEFAULT_DOMAINS_REL, SeedGenConfig, resolve_domains_config_path
from joryu.seed_gen.counts import count_by_domain
from joryu.seed_gen.pipeline import DEFAULT_BANK_REL
from joryu.seed_gen.writer import (
    DEFAULT_STATE_REL,
    atomic_append_jsonl,
    load_state,
    make_seed_row,
    save_state,
)

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


class PromptCheckStatusResponse(BaseModel):
    bank_total: int
    checked_count: int
    unchecked_count: int
    check_completed: bool


class PromptBankItem(BaseModel):
    key: str
    id: str | None = None
    prompt: str
    prompt_preview: str
    domain: str | None = None
    category: str | None = None
    checked: bool


class PromptBankListResponse(BaseModel):
    total: int
    checked_total: int
    unchecked_total: int
    offset: int
    limit: int
    items: list[PromptBankItem]


class MarkCheckedRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)
    all_unchecked: bool = False
    domain: str = ""


class MarkCheckedResponse(BaseModel):
    marked_count: int
    check_completed: bool


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


def _runner(request: Request) -> JobRunner:
    return request.app.state.job_runner


def _seed_gen_jobs(store: JobStore) -> list[JobRecord]:
    return [r for r in store.list_all() if r.kind == JobKind.SEED_GEN]


def _resolve_bank(repo_root: Any) -> Any:
    from pathlib import Path

    return Path(repo_root) / DEFAULT_BANK_REL


def _resolve_state(repo_root: Any) -> Any:
    from pathlib import Path

    return Path(repo_root) / DEFAULT_STATE_REL


def _load_bank_rows(repo_root: Any) -> list[Any]:
    bank = _resolve_bank(repo_root)
    return load_prompt_bank(bank) if bank.is_file() else []


def _prompt_preview(text: str, *, max_len: int = 120) -> str:
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1] + "…"


def _resolve_domains(repo_root: Any) -> SeedGenConfig:
    path = resolve_domains_config_path(repo_root, DEFAULT_DOMAINS_REL)
    return SeedGenConfig.load(path)


@router.get("/options")
def seed_gen_options(request: Request) -> dict[str, Any]:
    orchestrator = get_orchestrator(request)
    seed_ready = orchestrator.profile_ready(ModelProfile.SEED_GEN)
    judge_ready = orchestrator.profile_ready(ModelProfile.SCREENING)
    return {
        "defaults": {
            "bank": DEFAULT_BANK_REL,
            "domains_config": DEFAULT_DOMAINS_REL,
            "target_total": 230000,
        },
        "vllm_available": seed_ready,
        "seed_gen_ready": seed_ready,
        "judge_ready": judge_ready,
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

    # profile 起動/切替中でも enqueue する (JobRunner が profile を自動切替する)。
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


@status_router.get("/check/status", response_model=PromptCheckStatusResponse)
def prompt_check_status(request: Request) -> PromptCheckStatusResponse:
    repo_root = request.app.state.repo_root
    rows = _load_bank_rows(repo_root)
    state = load_state(_resolve_state(repo_root))
    status = compute_check_status(rows, state.prompt_check.checked_keys)
    return PromptCheckStatusResponse(
        bank_total=status.bank_total,
        checked_count=status.checked_count,
        unchecked_count=status.unchecked_count,
        check_completed=status.check_completed,
    )


@status_router.get("/prompts", response_model=PromptBankListResponse)
def list_prompt_bank(
    request: Request,
    offset: int = 0,
    limit: int = 50,
    domain: str = "",
    checked: str = "all",
) -> PromptBankListResponse:
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be 1..200")
    if checked not in ("all", "checked", "unchecked"):
        raise HTTPException(status_code=400, detail="checked must be all|checked|unchecked")

    repo_root = request.app.state.repo_root
    rows = _load_bank_rows(repo_root)
    state = load_state(_resolve_state(repo_root))
    checked_keys = state.prompt_check.checked_keys
    dom = domain.strip()

    filtered: list[Any] = []
    for row in rows:
        if dom and (row.domain or "") != dom:
            continue
        is_checked = prompt_check_key(row) in checked_keys
        if checked == "checked" and not is_checked:
            continue
        if checked == "unchecked" and is_checked:
            continue
        filtered.append(row)

    checked_total = sum(1 for row in rows if prompt_check_key(row) in checked_keys)
    page = filtered[offset : offset + limit]
    items = [
        PromptBankItem(
            key=prompt_check_key(row),
            id=row.id,
            prompt=row.prompt,
            prompt_preview=_prompt_preview(row.prompt),
            domain=row.domain,
            category=row.category,
            checked=prompt_check_key(row) in checked_keys,
        )
        for row in page
    ]
    return PromptBankListResponse(
        total=len(filtered),
        checked_total=checked_total,
        unchecked_total=len(rows) - checked_total,
        offset=offset,
        limit=limit,
        items=items,
    )


@status_router.post("/check/mark", response_model=MarkCheckedResponse)
def mark_prompts_checked(request: Request, body: MarkCheckedRequest) -> MarkCheckedResponse:
    if body.all_unchecked and body.keys:
        raise HTTPException(status_code=400, detail="keys and all_unchecked are mutually exclusive")

    repo_root = request.app.state.repo_root
    rows = _load_bank_rows(repo_root)
    state_path = _resolve_state(repo_root)
    state = load_state(state_path)

    if body.all_unchecked:
        marked = mark_all_unchecked(rows, state, domain=body.domain)
    else:
        keys = {k.strip() for k in body.keys if k.strip()}
        before = len(state.prompt_check.checked_keys)
        mark_checked(state, keys)
        marked = len(state.prompt_check.checked_keys) - before

    save_state(state_path, state)
    status = compute_check_status(rows, state.prompt_check.checked_keys)
    return MarkCheckedResponse(
        marked_count=marked,
        check_completed=status.check_completed,
    )
