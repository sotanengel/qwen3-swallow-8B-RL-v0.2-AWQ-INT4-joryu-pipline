"""RunnerStrategy テスト (#255)。"""

from __future__ import annotations

from joryu.jobs.models import (
    CurateJobSpec,
    DistillJobSpec,
    JobKind,
    JobRecord,
    JobStatus,
    SeedGenJobSpec,
)
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


def test_factory_build_job_command_seed_gen(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://localhost:8100")
    record = JobRecord(
        id="job-seed",
        kind=JobKind.SEED_GEN,
        status=JobStatus.QUEUED,
        spec=SeedGenJobSpec(fake_llm=True, domain="math"),
        created_at="2026-01-01T00:00:00Z",
    )
    cmd = RunnerStrategyFactory.build_job_command(tmp_path, record)
    assert "joryu.seed_gen.cli" in " ".join(cmd)
    assert "--fake-llm" in cmd


def test_curate_spec_screening_argv() -> None:
    spec = CurateJobSpec(screening=True, prompt_bank=True, src="data/prompts/b.jsonl")
    argv = spec.to_curate_argv()
    assert "--screening" in argv
    assert "--prompt-bank" in argv
    assert "--src" in argv
