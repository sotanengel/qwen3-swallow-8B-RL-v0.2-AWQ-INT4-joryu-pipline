"""Throughput ベンチ実行とメトリクス集計。"""

from __future__ import annotations

import copy
import logging
import time
from pathlib import Path
from typing import Any

from joryu.core.config import Config
from joryu.distill import run_distill
from joryu.io.jsonl import iter_jsonl
from joryu.tooling.truncation import record_looks_truncated
from joryu.vllm.protocol import SupportsChat

logger = logging.getLogger(__name__)


def _compute_throughput_metrics(
    records: list[dict[str, Any]], elapsed_sec: float
) -> dict[str, Any]:
    total_records = len(records)
    total_prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in records)
    total_completion_tokens = sum(int(r.get("completion_tokens") or 0) for r in records)
    total_generation_attempts = sum(int(r.get("generation_attempts") or 1) for r in records)

    truncated_count = sum(1 for r in records if record_looks_truncated(r))
    truncated_rate = truncated_count / total_records if total_records else 0.0

    elapsed = max(elapsed_sec, 1e-9)
    output_tok_per_sec = total_completion_tokens / elapsed
    prefill_tok_per_sec = total_prompt_tokens / elapsed
    return {
        "records": total_records,
        "truncated_rate": truncated_rate,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_generation_attempts": total_generation_attempts,
        "output_tok_per_sec": output_tok_per_sec,
        "prefill_tok_per_sec": prefill_tok_per_sec,
        # TTFT（初回応答）は分解が必要だが、Fake 実行では安定性が低いので省略。
    }


def run_throughput_bench(
    *,
    cfg: Config,
    bank_path: Path,
    out_path: Path,
    client: SupportsChat | None,
    count: int,
) -> dict[str, Any]:
    """distill を Fake/実クライアントで回し、壁時計ベースのメトリクスを返す。"""
    # CI では sleep を潰して高速化する（record_looks_truncated でしか sleep されないが保険）。
    bench_cfg = copy.deepcopy(cfg)
    bench_cfg.distill.min_interval_sec = 0.0

    start = time.perf_counter()
    run_distill(
        bench_cfg,
        bank_path=str(bank_path),
        out_path=str(out_path),
        client=client,
        count=count,
        redo_truncated=False,
        style_presets=None,
        stats_refresher=None,
        config_path=None,
    )
    elapsed = time.perf_counter() - start

    records = list(iter_jsonl(out_path, logger=logger, log_prefix="bench throughput"))
    metrics = _compute_throughput_metrics(records, elapsed)
    return metrics


__all__ = ["run_throughput_bench"]
