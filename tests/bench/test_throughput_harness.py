from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeVllmClient

from joryu.bench.compare import compare_throughput_metrics
from joryu.bench.prompts import read_prompt_bank_jsonl
from joryu.bench.throughput import run_throughput_bench
from joryu.core.config import Config


def test_throughput_metrics_deterministic(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    bank = repo / "tests" / "fixtures" / "bench" / "prompts.jsonl"
    baseline = repo / "tests" / "fixtures" / "bench" / "baseline_throughput.json"

    metrics_out = tmp_path / "throughput.jsonl"
    cfg = Config()
    # distill 側は tools.yaml / styles.yaml を読むが、参照解決は repo パス前提で成立する。

    client = FakeVllmClient(answer="今日は晴れです。", thinking=None)
    metrics = run_throughput_bench(
        cfg=cfg,
        bank_path=bank,
        out_path=metrics_out,
        client=client,
        count=50,
    )

    import json

    base = json.loads(baseline.read_text(encoding="utf-8"))
    compare_throughput_metrics(metrics=metrics, baseline=base)

    # sanity: bank は 50 行であるべき
    assert len(read_prompt_bank_jsonl(bank)) == 50
