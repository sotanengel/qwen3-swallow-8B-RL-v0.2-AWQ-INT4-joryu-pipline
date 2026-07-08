"""Quality ベンチ実行とシグナル集計。"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

from joryu.core.config import Config
from joryu.curate.signals import SignalResult
from joryu.curate.signals.quality import StyleFormat
from joryu.curate.signals.stat import LangJapanese, RepeatChar, RepeatNGram
from joryu.distill import run_distill
from joryu.io.jsonl import iter_jsonl
from joryu.tooling.truncation import record_looks_truncated
from joryu.vllm.protocol import SupportsChat

logger = logging.getLogger(__name__)


def _evaluate_quality_signals(cfg: Config, record: dict[str, Any]) -> list[SignalResult]:
    th = cfg.curate.thresholds
    lang = LangJapanese(th=th)
    rep_ng = RepeatNGram(th=th)
    rep_ch = RepeatChar(th=th)
    style = StyleFormat()
    return [
        lang.evaluate(record),
        rep_ng.evaluate(record),
        rep_ch.evaluate(record),
        style.evaluate(record),
    ]


def _compute_quality_metrics(cfg: Config, records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {
            "records": 0,
            "truncated_rate": 0.0,
            "pass_rate": 0.0,
            "hard_reject_count": 0,
        }

    truncated_count = sum(1 for r in records if record_looks_truncated(r))

    hard_reject_count = 0
    for r in records:
        results = _evaluate_quality_signals(cfg, r)
        if any(res.hard_reject for res in results):
            hard_reject_count += 1

    pass_count = total - hard_reject_count
    truncated_rate = truncated_count / total
    pass_rate = pass_count / total

    return {
        "records": total,
        "truncated_rate": truncated_rate,
        "pass_rate": pass_rate,
        "hard_reject_count": hard_reject_count,
    }


def run_quality_bench(
    *,
    cfg: Config,
    bank_path: Path,
    out_path: Path,
    client: SupportsChat | None,
    count: int,
) -> dict[str, Any]:
    """distill を Fake/実クライアントで回し、R-10 シグナルを集計する。"""
    bench_cfg = copy.deepcopy(cfg)
    bench_cfg.distill.min_interval_sec = 0.0

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

    records = list(iter_jsonl(out_path, logger=logger, log_prefix="bench quality"))
    return _compute_quality_metrics(cfg=bench_cfg, records=records)


__all__ = ["run_quality_bench"]
