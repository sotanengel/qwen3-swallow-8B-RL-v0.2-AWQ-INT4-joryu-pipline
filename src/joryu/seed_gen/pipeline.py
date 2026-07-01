"""seed_gen パイプライン (#319)。

モード:
- ``create``: LLM でプロンプトを生成し、Stage1 完全一致 dedup のみで bank へ追記。
- ``check``: 既存 bank を走査して Stage2 埋め込み類似 dedup を行い、類似行を
  ``data/prompts/rejected/similar.jsonl`` へ隔離する。LLM ベースの品質スクリーニングは
  従来通り ``joryu-curate --screening --prompt-bank`` (別ジョブ) が担当する。
"""

from __future__ import annotations

import logging
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joryu.jobs.models import SEED_GEN_MODE_CHECK, SEED_GEN_MODE_CREATE
from joryu.prompt_bank import load_prompt_bank
from joryu.prompt_dedup import ExactDedup
from joryu.seed_gen.config import SeedGenConfig
from joryu.seed_gen.counts import count_by_domain
from joryu.seed_gen.dedup import EmbeddingIndex, load_sentence_transformer_backend
from joryu.seed_gen.generator import (
    OpenAICompatibleSeedGenerator,
    SamplingParams,
)
from joryu.seed_gen.writer import (
    DomainState,
    SeedGenState,
    atomic_append_jsonl,
    load_state,
    make_seed_row,
    save_state,
)

logger = logging.getLogger(__name__)

DEFAULT_BANK_REL = "data/prompts/training_prompts.jsonl"
DEFAULT_REJECTED_REL = "data/prompts/rejected/similar.jsonl"
DEFAULT_BATCH_SIZE = 8
REJECT_RATE_ESCALATE = 0.8
COMPLETION_RATIO = 0.8


@dataclass
class PipelineOptions:
    bank_path: Path
    state_path: Path
    config: SeedGenConfig
    mode: str = SEED_GEN_MODE_CREATE
    sim_threshold: float = 0.85
    batch_size: int = DEFAULT_BATCH_SIZE
    resume: bool = False
    embed_model: str = "cl-nagoya/ruri-large"
    llm_base_url: str = ""
    llm_model: str = ""
    target_total_override: int | None = None
    rejected_path: Path | None = None
    log: Any = print


class _InterruptFlag:
    def __init__(self) -> None:
        self.triggered = False

    def mark(self, *_args: Any) -> None:
        self.triggered = True


def _resolve_batch_size(batch_size: int, remaining: int) -> int:
    if batch_size <= 0:
        return min(DEFAULT_BATCH_SIZE, max(1, remaining))
    return min(batch_size, max(1, remaining))


def estimate_plan(
    cfg: SeedGenConfig,
    existing_counts: dict[str, int],
) -> dict[str, Any]:
    gaps: dict[str, int] = {}
    for d in cfg.domains:
        have = existing_counts.get(d.key, 0)
        goal = d.target
        gaps[d.key] = max(0, goal - have)
    remaining = sum(gaps.values())
    return {
        "target_total": cfg.target_total,
        "existing_total": sum(existing_counts.values()),
        "existing_by_domain": existing_counts,
        "remaining_by_domain": gaps,
        "remaining_total": remaining,
    }


def _seed_domain_states(cfg: SeedGenConfig, state: SeedGenState) -> None:
    for d in cfg.domains:
        if d.key not in state.domains:
            state.domains[d.key] = DomainState()


def run_create_pipeline(opts: PipelineOptions) -> int:
    """LLM 生成 + Stage1 完全一致 dedup。"""
    cfg = opts.config
    if opts.target_total_override is not None:
        cfg = cfg.with_target_total(opts.target_total_override)

    rows = load_prompt_bank(opts.bank_path) if opts.bank_path.is_file() else []
    existing_counts = count_by_domain(rows, cfg)

    exact = ExactDedup()
    exact.seed_from_existing(r.prompt for r in rows)

    state = load_state(opts.state_path) if opts.resume else SeedGenState()
    _seed_domain_states(cfg, state)

    base_url = opts.llm_base_url or "http://127.0.0.1:8100/v1"
    gen = OpenAICompatibleSeedGenerator(
        base_url=base_url,
        model=opts.llm_model or "Qwen/Qwen2.5-7B-Instruct-AWQ",
    )

    interrupt = _InterruptFlag()
    signal.signal(signal.SIGINT, interrupt.mark)

    all_complete = True
    for domain in cfg.domains:
        goal = domain.target
        have = existing_counts.get(domain.key, 0)
        if have >= goal * COMPLETION_RATIO:
            continue
        all_complete = False
        dom_state = state.domains[domain.key]
        gap = max(0, goal - have)
        opts.log(f"[seed_gen create] domain={domain.key} gap={gap}")

        while gap > 0 and not interrupt.triggered:
            batch_n = _resolve_batch_size(opts.batch_size, gap)
            sampling = gen.next_sampling()

            generated = gen.generate_batch(domain=domain, n=batch_n, sampling=sampling)
            dom_state.generated += len(generated)
            accepted_rows: list[dict[str, Any]] = []
            rejected_exact = 0

            for prompt in generated:
                if exact.is_duplicate(prompt):
                    rejected_exact += 1
                    continue
                exact.add(prompt)
                accepted_rows.append(
                    make_seed_row(
                        prompt,
                        domain.key,
                        sampling={"temperature": sampling.temperature, "top_p": sampling.top_p},
                    )
                )
                gap -= 1
                dom_state.accepted += 1
                if gap <= 0:
                    break

            dom_state.rejected_exact += rejected_exact
            gen_total = len(generated)
            if gen_total and rejected_exact / gen_total > REJECT_RATE_ESCALATE:
                sampling = SamplingParams(
                    temperature=min(1.2, sampling.temperature + 0.1),
                    top_p=sampling.top_p,
                )

            if accepted_rows:
                atomic_append_jsonl(opts.bank_path, accepted_rows)
                existing_counts[domain.key] = existing_counts.get(domain.key, 0) + len(
                    accepted_rows
                )
                save_state(opts.state_path, state)

            if not generated:
                break

    save_state(opts.state_path, state)
    if interrupt.triggered:
        opts.log("[seed_gen create] interrupted; state saved")
        return 130
    if all_complete:
        opts.log("[seed_gen create] all domains >= 80% of target")
    return 0


def _rewrite_bank_without(bank_path: Path, remove_ids: set[str]) -> None:
    if not bank_path.is_file() or not remove_ids:
        return
    import json as _json
    import os as _os
    import tempfile as _tempfile

    tmp_fd, tmp_name = _tempfile.mkstemp(
        prefix=f".{bank_path.name}.",
        suffix=".tmp",
        dir=str(bank_path.parent),
    )
    kept = 0
    try:
        with _os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            for line in bank_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = _json.loads(line)
                except ValueError:
                    fh.write(line + "\n")
                    kept += 1
                    continue
                if str(obj.get("id", "")) in remove_ids:
                    continue
                fh.write(line + "\n")
                kept += 1
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp_name, bank_path)
    finally:
        if _os.path.exists(tmp_name):
            _os.unlink(tmp_name)
    logger.info("seed_gen check: rewrote bank with %d rows (removed %d)", kept, len(remove_ids))


def run_check_pipeline(opts: PipelineOptions) -> int:
    """既存 bank に対して Stage2 埋め込み類似 dedup を実行し、類似行を隔離する。"""
    bank_path = opts.bank_path
    if not bank_path.is_file():
        opts.log("[seed_gen check] bank not found; nothing to check")
        return 0
    rows = load_prompt_bank(bank_path)
    if len(rows) < 2:
        opts.log("[seed_gen check] bank has < 2 rows; nothing to compare")
        return 0

    opts.log(f"[seed_gen check] loading embedding backend: {opts.embed_model}")
    backend = load_sentence_transformer_backend(opts.embed_model)
    index = EmbeddingIndex(backend, threshold=opts.sim_threshold)

    rejected_path = opts.rejected_path or bank_path.parent / "rejected" / "similar.jsonl"
    rejected_path.parent.mkdir(parents=True, exist_ok=True)

    kept_prompts: list[str] = []
    remove_ids: set[str] = set()
    rejected_rows: list[dict[str, Any]] = []

    interrupt = _InterruptFlag()
    signal.signal(signal.SIGINT, interrupt.mark)

    for i, row in enumerate(rows):
        if interrupt.triggered:
            opts.log(f"[seed_gen check] interrupted at row {i}")
            break
        prompt = row.prompt
        if index.is_similar(prompt):
            row_id = getattr(row, "id", "") or ""
            if not row_id:
                # id が無い行はスキップ (削除できない)
                continue
            remove_ids.add(str(row_id))
            rejected_rows.append(
                {
                    "id": str(row_id),
                    "prompt": prompt,
                    "reason": "stage2_similar",
                    "threshold": opts.sim_threshold,
                }
            )
        else:
            index.add(prompt)
            kept_prompts.append(prompt)
        if (i + 1) % 100 == 0:
            opts.log(
                f"[seed_gen check] scanned {i + 1}/{len(rows)}"
                f" kept={len(kept_prompts)} rejected={len(rejected_rows)}"
            )

    if rejected_rows:
        atomic_append_jsonl(rejected_path, rejected_rows)
        _rewrite_bank_without(bank_path, remove_ids)

    # state.json の rejected_similar のみ更新
    state = load_state(opts.state_path)
    _seed_domain_states(opts.config, state)
    for row_meta in rejected_rows:
        # 元の PromptRow から domain を得る手段が無いので "unknown" 集計
        dom = state.domains.setdefault("_check", DomainState())
        dom.rejected_similar += 1
        _ = row_meta
    save_state(opts.state_path, state)

    opts.log(
        f"[seed_gen check] done: kept={len(kept_prompts)} rejected={len(rejected_rows)}"
        f" out={rejected_path}"
    )
    if interrupt.triggered:
        return 130
    return 0


def run_pipeline(opts: PipelineOptions) -> int:
    if opts.mode == SEED_GEN_MODE_CHECK:
        return run_check_pipeline(opts)
    if opts.mode == SEED_GEN_MODE_CREATE:
        return run_create_pipeline(opts)
    raise ValueError(f"unknown seed_gen mode: {opts.mode}")


__all__ = [
    "COMPLETION_RATIO",
    "DEFAULT_BANK_REL",
    "DEFAULT_REJECTED_REL",
    "PipelineOptions",
    "estimate_plan",
    "run_check_pipeline",
    "run_create_pipeline",
    "run_pipeline",
]
