from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import FakeVllmClient

from joryu.bench.compare import compare_quality_metrics
from joryu.bench.quality import run_quality_bench
from joryu.core.config import Config


def test_quality_metrics_deterministic(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    bank = repo / "tests" / "fixtures" / "bench" / "prompts.jsonl"
    baseline = repo / "tests" / "fixtures" / "bench" / "baseline_quality.json"

    out = tmp_path / "quality.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="今日は晴れです。", thinking=None)

    metrics = run_quality_bench(
        cfg=cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        count=50,
    )

    base = json.loads(baseline.read_text(encoding="utf-8"))
    compare_quality_metrics(metrics=metrics, baseline=base)
