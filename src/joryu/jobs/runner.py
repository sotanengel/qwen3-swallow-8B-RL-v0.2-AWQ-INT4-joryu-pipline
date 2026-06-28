"""蒸留ジョブのバックグラウンド実行。"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from joryu.distill import STATS_REFRESH_INTERVAL_SEC
from joryu.docker_paths import map_path_for_docker, resolve_host_repo_root
from joryu.job_process import terminate_process_tree
from joryu.jobs.models import (
    CurateJobSpec,
    DistillJobSpec,
    JobKind,
    JobRecord,
    JobStatus,
    SeedGenJobSpec,
)
from joryu.jobs.store import JobStore

if TYPE_CHECKING:
    from joryu.orchestrator.profile import ModelProfile
    from joryu.orchestrator.service import ModelOrchestrator

logger = logging.getLogger(__name__)

CURATE_JOBS_REL = "data/curated/jobs"


def default_jobs_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "jobs"


def should_use_compose_run(*, env: dict[str, str] | None = None) -> bool:
    """ホスト上で docker compose run を使うか（API コンテナ内は False）。"""
    e = os.environ if env is None else env
    if e.get("JORYU_USE_COMPOSE_RUN", "").lower() in ("1", "true", "yes"):
        return False
    return Path("/var/run/docker.sock").exists() and platform.system() != "Windows"


def should_use_api_docker_delegate(*, env: dict[str, str] | None = None) -> bool:
    """API コンテナ内から docker run デリゲートを使うか。"""
    e = os.environ if env is None else env
    return e.get("JORYU_USE_COMPOSE_RUN", "").lower() in ("1", "true", "yes")


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


def vllm_daemon_configured(*, env: dict[str, str] | None = None) -> bool:
    """常駐 vLLM デーモン URL が設定されているか。"""
    e = os.environ if env is None else env
    return bool(e.get("JORYU_VLLM_URL", "").strip())


def build_local_distill_command(repo_root: Path, spec: DistillJobSpec) -> list[str]:
    """API コンテナ内で HTTP デーモン経由 distill を実行 (GPU docker run 不要)。"""
    del repo_root
    return [
        sys.executable,
        "-m",
        "joryu.cli.distill",
        "--no-docker",
        "--config",
        spec.config,
        *spec.to_distill_argv(),
    ]


def build_local_seed_gen_command(repo_root: Path, spec: SeedGenJobSpec) -> list[str]:
    del repo_root
    return [
        sys.executable,
        "-m",
        "joryu.seed_gen.cli",
        *spec.to_seed_gen_argv(),
    ]


def build_local_curate_command(
    repo_root: Path,
    spec: CurateJobSpec,
    *,
    job_id: str,
) -> list[str]:
    del repo_root
    return [
        sys.executable,
        "-m",
        "joryu.cli.curate",
        "--config",
        spec.config,
        *_curate_argv_with_dst(spec, job_id),
    ]


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
    from joryu.docker_delegate import DEFAULT_IMAGE, build_docker_command
    from joryu.docker_runtime import prepare_distill_docker_mounts

    host_root = resolve_host_repo_root(repo_root)

    def _map(path: Path) -> Path:
        return map_path_for_docker(path, repo_root=repo_root, host_repo_root=host_root)

    config_path = (repo_root / spec.config).resolve()
    if should_use_api_docker_delegate():
        hf_cache: Path | str = "hf-cache"
    else:
        from joryu.docker_delegate import hf_cache_dir

        hf_cache_path = hf_cache_dir()
        hf_cache_path.mkdir(parents=True, exist_ok=True)
        hf_cache = _map(hf_cache_path)

    mounts = prepare_distill_docker_mounts(
        repo_root,
        config_path,
        config_rel=spec.config.replace("\\", "/"),
        map_path=_map,
        hf_cache=hf_cache,
        mount_styles=bool(spec.style),
    )

    cmd = build_docker_command(
        image=DEFAULT_IMAGE,
        cwd=host_root,
        config_path=mounts.config_path,
        config_rel=mounts.config_rel,
        src_dir=mounts.src_dir,
        data_dir=mounts.data_dir,
        dashboard_public_dir=mounts.dashboard_public,
        hf_cache=mounts.hf_cache,
        styles_path=mounts.styles_path,
        styles_rel=mounts.styles_rel,
        tools_path=mounts.tools_path,
        tools_rel=mounts.tools_rel,
        allocate_tty=False,
        extra_args=spec.to_distill_argv(),
    )
    cmd[0] = resolve_docker_bin()
    return cmd


def curate_job_dst(repo_root: Path, job_id: str) -> Path:
    """API 経由 curate ジョブの固定出力ディレクトリ。"""
    return repo_root / CURATE_JOBS_REL / job_id


def curate_job_dst_rel(job_id: str) -> str:
    return f"{CURATE_JOBS_REL}/{job_id}".replace("\\", "/")


def _curate_argv_with_dst(spec: CurateJobSpec, job_id: str) -> list[str]:
    return [*spec.to_curate_argv(), "--dst", curate_job_dst_rel(job_id)]


def build_job_command(repo_root: Path, record: JobRecord) -> list[str]:
    from joryu.jobs.strategy import RunnerStrategyFactory

    return RunnerStrategyFactory.build_job_command(repo_root, record)


def build_distill_command(repo_root: Path, spec: DistillJobSpec) -> list[str]:
    if vllm_daemon_configured():
        return build_local_distill_command(repo_root, spec)
    if should_use_api_docker_delegate():
        return build_docker_delegate_command(repo_root, spec)
    if should_use_compose_run():
        return build_compose_run_command(repo_root, spec)
    if platform.system() == "Windows":
        return build_docker_delegate_command(repo_root, spec)
    return build_compose_run_command(repo_root, spec)


def build_compose_run_curate_command(
    repo_root: Path,
    spec: CurateJobSpec,
    *,
    job_id: str,
) -> list[str]:
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
        "joryu-curate",
        "--config",
        spec.config,
        *_curate_argv_with_dst(spec, job_id),
    ]


def build_curate_docker_delegate_command(
    repo_root: Path,
    spec: CurateJobSpec,
    *,
    job_id: str,
) -> list[str]:
    from joryu.docker_delegate import DEFAULT_IMAGE, build_docker_command
    from joryu.docker_runtime import prepare_distill_docker_mounts

    host_root = resolve_host_repo_root(repo_root)

    def _map(path: Path) -> Path:
        return map_path_for_docker(path, repo_root=repo_root, host_repo_root=host_root)

    config_path = (repo_root / spec.config).resolve()
    if should_use_api_docker_delegate():
        hf_cache: Path | str = "hf-cache"
    else:
        from joryu.docker_delegate import hf_cache_dir

        hf_cache_path = hf_cache_dir()
        hf_cache_path.mkdir(parents=True, exist_ok=True)
        hf_cache = _map(hf_cache_path)

    mounts = prepare_distill_docker_mounts(
        repo_root,
        config_path,
        config_rel=spec.config.replace("\\", "/"),
        map_path=_map,
        hf_cache=hf_cache,
        mount_styles=False,
    )

    cmd = build_docker_command(
        image=DEFAULT_IMAGE,
        cwd=host_root,
        config_path=mounts.config_path,
        config_rel=mounts.config_rel,
        src_dir=mounts.src_dir,
        data_dir=mounts.data_dir,
        dashboard_public_dir=mounts.dashboard_public,
        hf_cache=mounts.hf_cache,
        styles_path=mounts.styles_path,
        styles_rel=mounts.styles_rel,
        tools_path=mounts.tools_path,
        tools_rel=mounts.tools_rel,
        allocate_tty=False,
        extra_args=_curate_argv_with_dst(spec, job_id),
        cli_module="joryu.cli.curate",
        native_flag=None,
    )
    cmd[0] = resolve_docker_bin()
    return cmd


def build_curate_command(repo_root: Path, spec: CurateJobSpec, *, job_id: str) -> list[str]:
    if vllm_daemon_configured():
        return build_local_curate_command(repo_root, spec, job_id=job_id)
    if should_use_api_docker_delegate():
        return build_curate_docker_delegate_command(repo_root, spec, job_id=job_id)
    if should_use_compose_run():
        return build_compose_run_curate_command(repo_root, spec, job_id=job_id)
    if platform.system() == "Windows":
        return build_curate_docker_delegate_command(repo_root, spec, job_id=job_id)
    return build_compose_run_curate_command(repo_root, spec, job_id=job_id)


@contextmanager
def _temporary_env(updates: dict[str, str]):
    """ジョブ実行中のみ環境変数を上書きする。"""
    old: dict[str, str | None] = {}
    try:
        for key, value in updates.items():
            old[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, previous in old.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _prepare_record_for_profile(
    record: JobRecord,
    profile: ModelProfile,
    orchestrator: ModelOrchestrator,
) -> dict[str, str]:
    """profile 別 URL を spec / env に注入。"""
    from joryu.orchestrator.profile import ModelProfile as MP

    spec = orchestrator.profiles.get(profile)
    env: dict[str, str] = {}
    if spec is None:
        return env
    if profile == MP.DISTILL:
        env["JORYU_VLLM_URL"] = f"http://{spec.service}:{spec.port}"
    elif profile == MP.SEED_GEN and isinstance(record.spec, SeedGenJobSpec):
        if not record.spec.llm_base_url:
            record.spec.llm_base_url = f"http://{spec.service}:{spec.port}/v1"
    elif profile == MP.SCREENING and isinstance(record.spec, CurateJobSpec):
        if not record.spec.judge_base_url:
            record.spec.judge_base_url = f"http://{spec.service}:{spec.port}"
    return env


def _inject_container_name(cmd: list[str], name: str) -> list[str]:
    """docker run / docker compose run コマンドに --name を挿入する。"""
    result = list(cmd)
    for i, arg in enumerate(result):
        if arg == "--rm" and i > 0 and result[i - 1] == "run":
            result.insert(i + 1, name)
            result.insert(i + 1, "--name")
            return result
    return result


def _stats_refresh_loop(
    refresh: Callable[[], None],
    stop_event: threading.Event,
    *,
    interval_sec: float | None = None,
) -> None:
    interval = STATS_REFRESH_INTERVAL_SEC if interval_sec is None else interval_sec
    while True:
        refresh()
        if stop_event.wait(interval):
            break


def run_subprocess_logged(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    on_process: Callable[[subprocess.Popen[str]], None] | None = None,
    subprocess_popen: Callable[..., subprocess.Popen[str]] | None = None,
) -> int:
    """subprocess を実行し stdout/stderr をログファイルへ逐次追記する。

    Popen を使うことで実行中のプロセスハンドルを ``on_process`` 経由で
    呼び出し側に渡せる。これによりキャンセル時に ``terminate()`` 可能。
    """
    popen = subprocess_popen or subprocess.Popen
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_fh:
        log_fh.write(f"[joryu-runner] {' '.join(cmd)}\n")
        log_fh.flush()
        proc = popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if on_process is not None:
            on_process(proc)
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)
            log_fh.flush()
        return proc.wait()


RunCommand = Callable[[list[str], Path, Path, Callable[[subprocess.Popen[str]], None] | None], int]


def _default_run_command(repo_root: Path) -> RunCommand:
    def _run(
        cmd: list[str],
        _cwd: Path,
        log_path: Path,
        on_process: Callable[[subprocess.Popen[str]], None] | None,
    ) -> int:
        return run_subprocess_logged(cmd, cwd=repo_root, log_path=log_path, on_process=on_process)

    return _run


class JobRunner:
    """単一 GPU 排他でジョブを FIFO 実行する。"""

    def __init__(
        self,
        store: JobStore,
        repo_root: Path,
        *,
        orchestrator: ModelOrchestrator | None = None,
        run_command: RunCommand | None = None,
        refresh_stats: Callable[[DistillJobSpec], int] | None = None,
        refresh_curation: Callable[[CurateJobSpec, str], int] | None = None,
        command_builder: Callable[[Path, JobRecord], list[str]] | None = None,
    ) -> None:
        self.store = store
        self.repo_root = repo_root
        self._orchestrator = orchestrator
        self._run_command: RunCommand = run_command or _default_run_command(repo_root)
        self._refresh_stats = refresh_stats or make_refresh_stats(repo_root)
        self._refresh_curation = refresh_curation or make_refresh_curation(repo_root)
        self._command_builder = command_builder or build_job_command
        self._lock = threading.Lock()
        self._queue: list[str] = []
        self._running_id: str | None = None
        self._running_process: subprocess.Popen[str] | None = None
        self._running_container_name: str | None = None
        self._cancel_requested: set[str] = set()

    @property
    def running_id(self) -> str | None:
        return self._running_id

    def reconcile_stale_jobs(self) -> int:
        """API 再起動時に orphaned な QUEUED/RUNNING 記録を終端状態へ回収する。"""
        count = 0
        for job in self.store.list_all():
            if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                continue
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now(UTC).isoformat()
            job.error = "recovered on api start"
            self.store.save(job)
            count += 1
        return count

    def enqueue(self, record: JobRecord) -> None:
        with self._lock:
            self._queue.append(record.id)
        self._maybe_start_next()

    def cancel(self, job_id: str) -> bool:
        """ジョブをキャンセルする。キュー内なら除去、実行中なら terminate。"""
        with self._lock:
            if job_id in self._queue:
                self._queue.remove(job_id)
                try:
                    record = self.store.load(job_id)
                except FileNotFoundError:
                    return False
                record.status = JobStatus.CANCELLED
                record.finished_at = datetime.now(UTC).isoformat()
                record.error = "cancelled by user"
                self.store.save(record)
                return True
            if job_id == self._running_id:
                self._cancel_requested.add(job_id)
                proc = self._running_process
                container_name = self._running_container_name
                if proc is not None and proc.poll() is None:
                    try:
                        terminate_process_tree(proc)
                    except OSError:
                        pass
                if container_name:
                    self._stop_container_async(container_name)
                return True
        return False

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

    def _set_running_process(self, proc: subprocess.Popen[str] | None) -> None:
        with self._lock:
            self._running_process = proc

    def _stop_container_async(self, container_name: str) -> None:
        """docker stop を別スレッドで非同期実行してコンテナを強制停止する。"""

        def _stop() -> None:
            try:
                subprocess.run(
                    [resolve_docker_bin(), "stop", "--time", "5", container_name],
                    check=False,
                    capture_output=True,
                )
            except OSError:
                pass

        threading.Thread(target=_stop, daemon=True).start()

    def _run_job(self, job_id: str) -> None:
        from joryu.orchestrator.required import required_profile

        record = self.store.load(job_id)
        record.status = JobStatus.RUNNING
        record.started_at = datetime.now(UTC).isoformat()
        self.store.save(record)

        profile = required_profile(record)
        profile_env: dict[str, str] = {}
        if self._orchestrator is not None:

            def _probe_log(message: str) -> None:
                self.store.append_log(job_id, message + "\n")

            try:
                self._orchestrator.ensure_profile(profile, log=_probe_log)
            except RuntimeError as exc:
                self.store.append_log(job_id, f"[joryu-runner] {exc}\n")
                record.status = JobStatus.FAILED
                record.error = str(exc)
                record.exit_code = 1
                record.finished_at = datetime.now(UTC).isoformat()
                self.store.save(record)
                with self._lock:
                    self._running_id = None
                    self._running_process = None
                self._maybe_start_next()
                return
            profile_env = _prepare_record_for_profile(record, profile, self._orchestrator)

        container_name = f"joryu-job-{job_id}"
        with self._lock:
            self._running_container_name = container_name

        log_path = self.store.log_path(job_id)
        exit_code = 1
        stop_refresh = threading.Event()
        refresh_thread: threading.Thread | None = None
        if record.kind == JobKind.DISTILL and isinstance(record.spec, DistillJobSpec):
            from joryu.preflight import (
                PreflightError,
                ensure_dashboard_data_paths,
                ensure_vllm_limits,
            )

            ensure_dashboard_data_paths(self.repo_root)

            def _probe_log(message: str) -> None:
                self.store.append_log(job_id, message + "\n")

            try:
                ensure_vllm_limits(
                    self.repo_root,
                    up_services=["api", "joryu"],
                    log=_probe_log,
                )
            except PreflightError as exc:
                self.store.append_log(job_id, f"[joryu-runner] {exc}\n")
                record.status = JobStatus.FAILED
                record.error = str(exc)
                record.exit_code = 1
                record.finished_at = datetime.now(UTC).isoformat()
                self.store.save(record)
                with self._lock:
                    self._running_id = None
                    self._running_process = None
                self._maybe_start_next()
                return

            def _refresh_stats_loop() -> None:
                self._refresh_stats(record.spec)

            refresh_thread = threading.Thread(
                target=_stats_refresh_loop,
                args=(_refresh_stats_loop, stop_refresh),
                daemon=True,
            )
            refresh_thread.start()
        elif record.kind == JobKind.CURATE and isinstance(record.spec, CurateJobSpec):
            curate_spec = record.spec

            def _refresh_curation_loop() -> None:
                self._refresh_curation(curate_spec, job_id)

            refresh_thread = threading.Thread(
                target=_stats_refresh_loop,
                args=(_refresh_curation_loop, stop_refresh),
                daemon=True,
            )
            refresh_thread.start()

        try:
            cmd = self._command_builder(self.repo_root, record)
            cmd = _inject_container_name(cmd, container_name)
            with _temporary_env(profile_env):
                exit_code = self._run_command(
                    cmd, self.repo_root, log_path, self._set_running_process
                )
            record.exit_code = exit_code
            if exit_code != 0:
                label = (
                    "curate"
                    if record.kind == JobKind.CURATE
                    else "seed_gen"
                    if record.kind == JobKind.SEED_GEN
                    else "distill"
                )
                record.error = f"{label} exited with code {exit_code}"
        except OSError as exc:
            record.exit_code = 1
            logger.exception("job failed", extra={"job_id": job_id})
            self.store.append_log(job_id, f"[joryu-runner] error: {exc}\n")
            record.error = str(exc)
        except Exception as exc:
            record.exit_code = 1
            logger.exception("job failed", extra={"job_id": job_id})
            self.store.append_log(job_id, f"[joryu-runner] error: {exc}\n")
            record.error = str(exc)
        finally:
            stop_refresh.set()
            if refresh_thread is not None:
                refresh_thread.join(timeout=1.0)

        record.finished_at = datetime.now(UTC).isoformat()
        with self._lock:
            cancelled = job_id in self._cancel_requested
            self._cancel_requested.discard(job_id)
            self._running_process = None
            self._running_container_name = None
        if cancelled:
            record.status = JobStatus.CANCELLED
            record.error = "cancelled by user"
            self.store.append_log(job_id, "[joryu-runner] cancelled by user\n")
        else:
            record.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        self.store.save(record)

        if record.kind == JobKind.DISTILL and isinstance(record.spec, DistillJobSpec):
            self._refresh_stats(record.spec)
        elif record.kind == JobKind.CURATE and isinstance(record.spec, CurateJobSpec):
            self._refresh_curation(record.spec, job_id)

        if self._orchestrator is not None:
            try:
                self._orchestrator.maybe_auto_restore(
                    log=lambda msg: self.store.append_log(job_id, msg + "\n"),
                )
            except RuntimeError as exc:
                logger.error("auto_restore failed", exc_info=True)
                self.store.append_log(job_id, f"[joryu-runner] auto_restore failed: {exc}\n")

        with self._lock:
            self._running_id = None
        self._maybe_start_next()


def make_refresh_stats(repo_root: Path) -> Callable[[DistillJobSpec], int]:
    """ジョブ成功後に repo_root 基準で stats.json を更新する。"""

    def refresh_stats(spec: DistillJobSpec) -> int:
        from joryu.cli.stats import main as stats_main
        from joryu.stats import resolve_stats_output_path

        cfg = repo_root / spec.config
        out = resolve_stats_output_path(repo_root=repo_root)
        if out is None:
            return 1
        return stats_main(["--config", str(cfg), "--output", str(out)])

    return refresh_stats


def make_refresh_curation(repo_root: Path) -> Callable[[CurateJobSpec, str], int]:
    """curate ジョブ実行中/終了時に curation.json を更新する。"""

    def refresh_curation(_spec: CurateJobSpec, job_id: str) -> int:
        from joryu.curate.stats import write_curation_json
        from joryu.paths import CURATION_JSON_REL

        scores = curate_job_dst(repo_root, job_id) / "scores.jsonl"
        if not scores.exists():
            return 0
        out = repo_root / CURATION_JSON_REL
        write_curation_json(scores, out)
        return 0

    return refresh_curation


def _default_refresh_stats(spec: DistillJobSpec) -> int:
    from joryu.cli.stats import main as stats_main

    argv = ["--config", spec.config]
    return stats_main(argv)
