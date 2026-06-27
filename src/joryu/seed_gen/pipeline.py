"""seed_gen パイプライン (#319)。"""

from __future__ import annotations

import logging
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joryu.prompt_bank import load_prompt_bank
from joryu.prompt_dedup import ExactDedup
from joryu.seed_gen.config import SeedGenConfig
from joryu.seed_gen.counts import count_by_domain
from joryu.seed_gen.dedup import (
    EmbeddingIndex,
    FakeEmbeddingBackend,
    try_sentence_transformer_backend,
)
from joryu.seed_gen.generator import (
    FakeSeedGenerator,
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
DEFAULT_BATCH_SIZE = 8
REJECT_RATE_ESCALATE = 0.8
COMPLETION_RATIO = 0.8


@dataclass
class PipelineOptions:
    bank_path: Path
    state_path: Path
    config: SeedGenConfig
    sim_threshold: float = 0.85
    batch_size: int = DEFAULT_BATCH_SIZE
    dry_run: bool = False
    resume: bool = False
    fake_llm: bool = False
    embed_model: str = "cl-nagoya/ruri-large"
    llm_base_url: str = ""
    llm_model: str = ""
    target_total_override: int | None = None
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


def run_pipeline(opts: PipelineOptions) -> int:
    cfg = opts.config
    if opts.target_total_override is not None:
        cfg = cfg.with_target_total(opts.target_total_override)

    rows = load_prompt_bank(opts.bank_path) if opts.bank_path.is_file() else []
    existing_counts = count_by_domain(rows, cfg)
    plan = estimate_plan(cfg, existing_counts)

    if opts.dry_run:
        logger.info("target_total: %s", cfg.target_total)
        logger.info("existing: %s (%s)", plan["existing_total"], plan["existing_by_domain"])
        logger.info("remaining: %s (%s)", plan["remaining_total"], plan["remaining_by_domain"])
        rate = 2.5
        est_hours = plan["remaining_total"] / rate / 3600 if plan["remaining_total"] else 0
        logger.info(
            "estimated time: %.1fh (at %s prompt/s, reject rate 30%%)",
            est_hours,
            rate,
        )
        return 0

    exact = ExactDedup()
    prompts = [r.prompt for r in rows]
    exact.seed_from_existing(prompts)

    if opts.fake_llm:
        embed_backend = FakeEmbeddingBackend()
    else:
        embed_backend = try_sentence_transformer_backend(opts.embed_model) or FakeEmbeddingBackend()
    embed_index = EmbeddingIndex(embed_backend, threshold=opts.sim_threshold)
    embed_index.seed_from_existing(prompts)

    state = load_state(opts.state_path) if opts.resume else SeedGenState()
    for d in cfg.domains:
        if d.key not in state.domains:
            state.domains[d.key] = DomainState()

    if opts.fake_llm:
        gen: Any = FakeSeedGenerator()
    else:
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
        opts.log(f"[seed_gen] domain={domain.key} gap={gap}")

        while gap > 0 and not interrupt.triggered:
            batch_n = _resolve_batch_size(opts.batch_size, gap)
            if hasattr(gen, "next_sampling"):
                sampling = gen.next_sampling()
            else:
                sampling = SamplingParams(temperature=0.9, top_p=0.95)

            generated = gen.generate_batch(domain=domain, n=batch_n, sampling=sampling)
            dom_state.generated += len(generated)
            accepted_rows: list[dict[str, Any]] = []
            rejected_exact = 0
            rejected_similar = 0

            for prompt in generated:
                if exact.is_duplicate(prompt):
                    rejected_exact += 1
                    continue
                if embed_index.is_similar(prompt):
                    rejected_similar += 1
                    continue
                exact.add(prompt)
                embed_index.add(prompt)
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
            dom_state.rejected_similar += rejected_similar
            reject_total = rejected_exact + rejected_similar
            gen_total = len(generated)
            if gen_total and reject_total / gen_total > REJECT_RATE_ESCALATE:
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
        opts.log("[seed_gen] interrupted; state saved")
        return 130
    if all_complete:
        opts.log("[seed_gen] all domains >= 80% of target")
    return 0


__all__ = [
    "COMPLETION_RATIO",
    "DEFAULT_BANK_REL",
    "PipelineOptions",
    "estimate_plan",
    "run_pipeline",
]
