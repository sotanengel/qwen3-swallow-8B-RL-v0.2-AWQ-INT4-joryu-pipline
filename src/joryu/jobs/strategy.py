"""RunnerStrategy ABC と Factory (#255)。"""

from __future__ import annotations

import platform
from abc import ABC, abstractmethod
from pathlib import Path

from joryu.jobs.models import CurateJobSpec, DistillJobSpec, JobKind, JobRecord, SeedGenJobSpec
from joryu.jobs.runner import (
    build_compose_run_command,
    build_compose_run_curate_command,
    build_curate_docker_delegate_command,
    build_docker_delegate_command,
    build_local_curate_command,
    build_local_distill_command,
    build_local_seed_gen_command,
    should_use_api_docker_delegate,
    should_use_compose_run,
    vllm_daemon_configured,
)


class RunnerStrategy(ABC):
    """ジョブ実行コマンド組み立て Strategy。"""

    @abstractmethod
    def build_distill_command(self, repo_root: Path, spec: DistillJobSpec) -> list[str]: ...

    @abstractmethod
    def build_curate_command(
        self,
        repo_root: Path,
        spec: CurateJobSpec,
        *,
        job_id: str,
    ) -> list[str]: ...

    @abstractmethod
    def build_seed_gen_command(self, repo_root: Path, spec: SeedGenJobSpec) -> list[str]: ...


class LocalRunnerStrategy(RunnerStrategy):
    def build_distill_command(self, repo_root: Path, spec: DistillJobSpec) -> list[str]:
        return build_local_distill_command(repo_root, spec)

    def build_curate_command(
        self,
        repo_root: Path,
        spec: CurateJobSpec,
        *,
        job_id: str,
    ) -> list[str]:
        return build_local_curate_command(repo_root, spec, job_id=job_id)

    def build_seed_gen_command(self, repo_root: Path, spec: SeedGenJobSpec) -> list[str]:
        return build_local_seed_gen_command(repo_root, spec)


class ComposeRunnerStrategy(RunnerStrategy):
    def build_distill_command(self, repo_root: Path, spec: DistillJobSpec) -> list[str]:
        return build_compose_run_command(repo_root, spec)

    def build_curate_command(
        self,
        repo_root: Path,
        spec: CurateJobSpec,
        *,
        job_id: str,
    ) -> list[str]:
        return build_compose_run_curate_command(repo_root, spec, job_id=job_id)

    def build_seed_gen_command(self, repo_root: Path, spec: SeedGenJobSpec) -> list[str]:
        return build_local_seed_gen_command(repo_root, spec)


class DockerRunnerStrategy(RunnerStrategy):
    def build_distill_command(self, repo_root: Path, spec: DistillJobSpec) -> list[str]:
        return build_docker_delegate_command(repo_root, spec)

    def build_curate_command(
        self,
        repo_root: Path,
        spec: CurateJobSpec,
        *,
        job_id: str,
    ) -> list[str]:
        return build_curate_docker_delegate_command(repo_root, spec, job_id=job_id)

    def build_seed_gen_command(self, repo_root: Path, spec: SeedGenJobSpec) -> list[str]:
        return build_local_seed_gen_command(repo_root, spec)


class RunnerStrategyFactory:
    """環境に応じた RunnerStrategy を返す。"""

    @staticmethod
    def resolve(*, env: dict[str, str] | None = None) -> RunnerStrategy:
        if vllm_daemon_configured(env=env):
            return LocalRunnerStrategy()
        if should_use_api_docker_delegate(env=env):
            return DockerRunnerStrategy()
        if should_use_compose_run(env=env):
            return ComposeRunnerStrategy()
        if platform.system() == "Windows":
            return DockerRunnerStrategy()
        return ComposeRunnerStrategy()

    @staticmethod
    def build_job_command(repo_root: Path, record: JobRecord) -> list[str]:
        strategy = RunnerStrategyFactory.resolve()
        if record.kind == JobKind.CURATE:
            assert isinstance(record.spec, CurateJobSpec)
            return strategy.build_curate_command(repo_root, record.spec, job_id=record.id)
        if record.kind == JobKind.SEED_GEN:
            assert isinstance(record.spec, SeedGenJobSpec)
            return strategy.build_seed_gen_command(repo_root, record.spec)
        assert isinstance(record.spec, DistillJobSpec)
        return strategy.build_distill_command(repo_root, record.spec)


__all__ = [
    "ComposeRunnerStrategy",
    "DockerRunnerStrategy",
    "LocalRunnerStrategy",
    "RunnerStrategy",
    "RunnerStrategyFactory",
]
