"""蒸留ジョブのバックグラウンド実行。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from joryu.docker_paths import map_path_for_docker, resolve_host_repo_root
from joryu.jobs.models import DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.store import JobStore


def default_jobs_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "jobs"


def should_use_compose_run(*, env: dict[str, str] | None = None) -> bool:
    """API コンテナ内など docker compose run を使うか。"""
    e = os.environ if env is None else env
    flag = e.get("JORYU_USE_COMPOSE_RUN", "").lower()
    if flag in ("1", "true", "yes"):
        return True
    return Path("/var/run/docker.sock").exists() and platform.system() != "Windows"


def resolve_docker_bin() -> str:
    """docker CLI のパス。API コンテナ (DooD) やホスト実行で使用。"""
    path = shutil.which("docker")
    if path:
        return path
    msg = (
        "docker CLI not found in PATH. "
        "API コンテナからジョブ実行する場合は api イメージを再ビルドしてください "
        "(`docker compose build api`)."
    )
    raise FileNotFoundError(msg)


def build_compose_run_command(repo_root: Path, spec: DistillJobSpec) -> list[str]:
    host_root = resolve_host_repo_root(repo_root)
    compose_file = host_root / "docker-compose.yml"
    return [
        resolve_docker_bin(),
        "compose",
        "-f",
        str(compose_file),
        "--project-directory",
        str(host_root),
        "run",
        "--rm",
        "joryu",
        "joryu-distill",
        "--no-docker",
        "--config",
        spec.config,
        *spec.to_distill_argv(),
    ]


def build_docker_delegate_command(repo_root: Path, spec: DistillJobSpec) -> list[str]:
    from joryu.config import load_config
    from joryu.docker_delegate import DEFAULT_IMAGE, build_docker_command, hf_cache_dir

    host_root = resolve_host_repo_root(repo_root)

    def _map(path: Path) -> Path:
        return map_path_for_docker(path, repo_root=repo_root, host_repo_root=host_root)

    config_path = (repo_root / spec.config).resolve()
    cfg = load_config(config_path)
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    hf_cache = hf_cache_dir()
    hf_cache.mkdir(parents=True, exist_ok=True)
    src_dir = (repo_root / "src").resolve()

    styles_path = None
    styles_rel = None
    if spec.style:
        styles_rel = cfg.distill.styles_file
        candidate = (config_path.parent / styles_rel).resolve()
        if candidate.exists():
            styles_path = candidate

    return build_docker_command(
        image=DEFAULT_IMAGE,
        cwd=host_root,
        config_path=_map(config_path),
        config_rel=spec.config.replace("\\", "/"),
        src_dir=_map(src_dir),
        data_dir=_map(data_dir),
        hf_cache=_map(hf_cache),
        styles_path=_map(styles_path) if styles_path is not None else None,
        styles_rel=styles_rel,
        allocate_tty=False,
        extra_args=spec.to_distill_argv(),
    )


def build_job_command(repo_root: Path, spec: DistillJobSpec) -> list[str]:
    if should_use_compose_run():
        return build_compose_run_command(repo_root, spec)
    if platform.system() == "Windows":
        return build_docker_delegate_command(repo_root, spec)
    return build_compose_run_command(repo_root, spec)


def run_subprocess_logged(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """subprocess を実行し stdout/stderr をログファイルへ追記する。"""
    runner = subprocess_run or subprocess.run
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_fh:
        log_fh.write(f"[joryu-runner] {' '.join(cmd)}\n")
        log_fh.flush()
        proc = runner(
            cmd,
            cwd=resolve_host_repo_root(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if proc.stdout:
            log_fh.write(proc.stdout)
            if not proc.stdout.endswith("\n"):
                log_fh.write("\n")
        return proc.returncode


class JobRunner:
    """単一 GPU 排他でジョブを FIFO 実行する。"""

    def __init__(
        self,
        store: JobStore,
        repo_root: Path,
        *,
        run_command: Callable[[list[str], Path, Path], int] | None = None,
        refresh_stats: Callable[[DistillJobSpec], int] | None = None,
        command_builder: Callable[[Path, DistillJobSpec], list[str]] | None = None,
    ) -> None:
        self.store = store
        self.repo_root = repo_root
        self._run_command = run_command or (
            lambda cmd, _cwd, log_path: run_subprocess_logged(cmd, cwd=repo_root, log_path=log_path)
        )
        self._refresh_stats = refresh_stats or _default_refresh_stats
        self._command_builder = command_builder or build_job_command
        self._lock = threading.Lock()
        self._queue: list[str] = []
        self._running_id: str | None = None

    @property
    def running_id(self) -> str | None:
        return self._running_id

    def enqueue(self, record: JobRecord) -> None:
        with self._lock:
            self._queue.append(record.id)
        self._maybe_start_next()

    def _maybe_start_next(self) -> None:
        with self._lock:
            if self._running_id is not None:
                return
            if not self._queue:
                return
            job_id = self._queue.pop(0)
            self._running_id = job_id
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()

    def _run_job(self, job_id: str) -> None:
        record = self.store.load(job_id)
        record.status = JobStatus.RUNNING
        record.started_at = datetime.now(UTC).isoformat()
        self.store.save(record)

        log_path = self.store.log_path(job_id)
        exit_code = 1
        try:
            cmd = self._command_builder(self.repo_root, record.spec)
            exit_code = self._run_command(cmd, self.repo_root, log_path)
            record.exit_code = exit_code
            if exit_code != 0:
                record.error = f"distill exited with code {exit_code}"
        except OSError as exc:
            record.exit_code = 1
            self.store.append_log(job_id, f"[joryu-runner] error: {exc}\n")
            record.error = str(exc)
        except Exception as exc:
            record.exit_code = 1
            self.store.append_log(job_id, f"[joryu-runner] error: {exc}\n")
            record.error = str(exc)

        record.finished_at = datetime.now(UTC).isoformat()
        record.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        self.store.save(record)

        if exit_code == 0:
            self._refresh_stats(record.spec)

        with self._lock:
            self._running_id = None
        self._maybe_start_next()


def _default_refresh_stats(spec: DistillJobSpec) -> int:
    from joryu.cli.stats import main as stats_main

    argv = ["--config", spec.config]
    return stats_main(argv)
