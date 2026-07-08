from __future__ import annotations

import json
from pathlib import Path

from joryu.bench.report import build_bench_report, write_report_json
from joryu.core.config import Config


def test_build_bench_report_schema(monkeypatch) -> None:
    cfg = Config()
    monkeypatch.setattr("joryu.bench.report._get_git_sha", lambda: "sha-test")
    monkeypatch.setattr("joryu.bench.report._get_gpu_name", lambda: "gpu-test")

    metrics = {"records": 1}
    rep = build_bench_report(cfg=cfg, metrics=metrics, kind="throughput")

    assert rep["kind"] == "throughput"
    assert rep["config_fingerprint"] == cfg.fingerprint()
    assert rep["git_sha"] == "sha-test"
    assert rep["gpu_name"] == "gpu-test"
    assert rep["metrics"] == metrics
    assert isinstance(rep["timestamp"], str)


def test_write_report_json(tmp_path: Path) -> None:
    cfg = Config()
    rep = {
        "kind": "throughput",
        "timestamp": "x",
        "config_fingerprint": cfg.fingerprint(),
        "git_sha": "g",
        "gpu_name": "u",
        "metrics": {},
    }

    out = tmp_path / "report.json"
    write_report_json(out, rep)

    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == rep
