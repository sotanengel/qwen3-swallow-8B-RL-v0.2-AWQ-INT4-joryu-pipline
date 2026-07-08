from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.core.config import load_config
from joryu.distill import DistillPipeline, run_distill
from tests.conftest import FakeVllmClient


def test_load_config_default_min_interval_is_0(tmp_path: Path) -> None:
    # distill セクションを省略した場合に既定が使われること。
    yaml_text = """
model:
  temperature: 0.6
"""
    path = tmp_path / "c.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config(path)
    assert cfg.distill.min_interval_sec == pytest.approx(0.0)


def test_pipeline_passes_min_interval_sec_from_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(json.dumps({"prompt": "P"}) + "\n", encoding="utf-8")

    out = tmp_path / "out.jsonl"

    yaml_text = """
distill:
  min_interval_sec: 1.0
"""
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_config(cfg_path)

    # distill パイプラインが retry.generate_until_complete へ渡す値を捕捉する。
    seen: dict[str, float] = {}

    def _fake_generate_until_complete(*_args, **kwargs):
        seen["min_interval_sec"] = float(kwargs["min_interval_sec"])
        return {"answer": "ok", "finish_reason": "stop"}, 1

    monkeypatch.setattr(
        "joryu.distill.pipeline.generate_until_complete",
        _fake_generate_until_complete,
    )

    run_distill(
        cfg,
        bank_path=prompts,
        out_path=out,
        client=FakeVllmClient(answer="unused", thinking=None),
        count=1,
        pipeline=DistillPipeline(stages=()),
    )

    assert seen["min_interval_sec"] == pytest.approx(1.0)
