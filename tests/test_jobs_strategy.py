"""RunnerStrategy テスト (#255)。"""

from __future__ import annotations

from joryu.jobs.models import DistillJobSpec, JobKind, JobRecord, JobStatus
from joryu.jobs.strategy import (
    ComposeRunnerStrategy,
    LocalRunnerStrategy,
    RunnerStrategyFactory,
)


def test_runner_strategy_factory_local_when_vllm_url(monkeypatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://localhost:8100")
    strategy = RunnerStrategyFactory.resolve()
    assert isinstance(strategy, LocalRunnerStrategy)


def test_compose_strategy_builds_distill_command(tmp_path) -> None:
    spec = DistillJobSpec(config="config.yaml")
    cmd = ComposeRunnerStrategy().build_distill_command(tmp_path, spec)
    assert "compose" in cmd
    assert "joryu-distill" in cmd


def test_factory_build_job_command_distill(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://localhost:8100")
    record = JobRecord(
        id="job-1",
        kind=JobKind.DISTILL,
        status=JobStatus.QUEUED,
        spec=DistillJobSpec(config="config.yaml"),
        created_at="2026-01-01T00:00:00Z",
    )
    cmd = RunnerStrategyFactory.build_job_command(tmp_path, record)
    assert "joryu.cli.distill" in " ".join(cmd) or "distill" in cmd[-1]
