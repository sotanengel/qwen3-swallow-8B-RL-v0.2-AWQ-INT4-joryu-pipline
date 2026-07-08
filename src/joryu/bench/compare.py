"""Benchmark 結果とベースラインの差分判定。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QualityCompareThresholds:
    # 計画: pass rate を -2pt 以内に抑える
    pass_rate_drop_max: float = 0.02
    # 計画: 打ち切り率を相対 ±10% 程度で許容
    truncated_rate_rel_tolerance: float = 0.10


_DEFAULT_QUALITY_THRESHOLDS = QualityCompareThresholds()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_quality_metrics(
    metrics: dict[str, Any],
    baseline: dict[str, Any],
    *,
    thresholds: QualityCompareThresholds | None = None,
) -> None:
    """Quality metrics がベースラインから大きく劣化していないことを assert。"""
    if thresholds is None:
        thresholds = _DEFAULT_QUALITY_THRESHOLDS
    assert int(metrics["records"]) == int(baseline["records"])

    base_pass = float(baseline["pass_rate"])
    cur_pass = float(metrics["pass_rate"])
    assert cur_pass + thresholds.pass_rate_drop_max >= base_pass, (
        f"pass_rate dropped too much: baseline={base_pass} current={cur_pass}"
    )

    base_trunc = float(baseline.get("truncated_rate", 0.0))
    cur_trunc = float(metrics.get("truncated_rate", 0.0))
    if base_trunc > 0:
        rel = abs(cur_trunc - base_trunc) / base_trunc
        assert rel <= thresholds.truncated_rate_rel_tolerance, (
            f"truncated_rate changed too much: baseline={base_trunc} current={cur_trunc}"
        )
    else:
        assert cur_trunc <= 0.05, f"truncated_rate should stay near 0, got {cur_trunc}"

    # hard reject count は厳しめ（baseline と一致を基本にする）
    assert int(metrics["hard_reject_count"]) == int(baseline["hard_reject_count"])


def compare_throughput_metrics(metrics: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Throughput metrics が決定的なトークン集計と一致することを assert。"""
    assert int(metrics["records"]) == int(baseline["records"])
    assert int(metrics["total_prompt_tokens"]) == int(baseline["total_prompt_tokens"])
    assert int(metrics["total_completion_tokens"]) == int(baseline["total_completion_tokens"])
    assert int(metrics["total_generation_attempts"]) == int(baseline["total_generation_attempts"])
