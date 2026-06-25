"""distill_live.py: 蒸留 live アラート状態。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.distill import default_stats_refresher
from joryu.distill_live import DistillLiveState


def test_default_stats_refresher_includes_distill_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "data" / "distilled" / "responses.jsonl"
    out.parent.mkdir(parents=True)
    out.write_text(
        '{"prompt":"P","answer":"完了。","finish_reason":"stop","model":"M"}\n',
        encoding="utf-8",
    )
    stats_path = tmp_path / "dashboard" / "public" / "stats.json"

    DistillLiveState.begin()
    try:
        DistillLiveState.report_retry(
            run_key='{"prompt": "P"}',
            prompt="長いプロンプト",
            style_id="prose",
            attempts=3,
        )
        default_stats_refresher(out)
    finally:
        DistillLiveState.end()

    data = json.loads(stats_path.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["distill_live"]["active"] is True
    assert len(data["distill_live"]["truncation_retries"]) == 1
    assert data["distill_live"]["truncation_retries"][0]["attempts"] == 3


def test_distill_live_ignores_retries_below_threshold() -> None:
    DistillLiveState.begin()
    try:
        DistillLiveState.report_retry(
            run_key="k",
            prompt="P",
            style_id=None,
            attempts=2,
        )
        live = DistillLiveState.to_dict()
        assert live["truncation_retries"] == []
    finally:
        DistillLiveState.end()
