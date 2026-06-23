"""jobs/runner.py のユニットテスト。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from joryu.jobs.models import CurateJobSpec, DistillJobSpec, JobKind, JobRecord, JobStatus
from joryu.jobs.runner import (
    JobRunner,
    _inject_container_name,
    build_curate_command,
    build_job_command,
    curate_job_dst_rel,
    make_refresh_stats,
    resolve_docker_bin,
    should_use_api_docker_delegate,
    should_use_compose_run,
)
from joryu.jobs.store import JobStore


@pytest.fixture(autouse=True)
def _skip_vllm_probe_in_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("joryu.preflight.ensure_vllm_limits", lambda *_args, **_kwargs: None)


def test_build_job_command_api_delegate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_USE_COMPOSE_RUN", "1")
    monkeypatch.setattr("joryu.jobs.runner.resolve_docker_bin", lambda: "/usr/bin/docker")
    host_root = Path("C:/repo")
    monkeypatch.setattr("joryu.jobs.runner.resolve_host_repo_root", lambda _root: host_root)
    (tmp_path / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    spec = DistillJobSpec(count=3, mode="nothinking")
    record = JobRecord.create(spec)
    cmd = build_job_command(tmp_path, record)
    assert cmd[0:3] == ["/usr/bin/docker", "run", "--rm"]
    assert "joryu:latest" in cmd
    assert "hf-cache:/root/.cache/huggingface" in cmd
    assert "joryu.cli.distill" in cmd
    assert "--count" in cmd and "3" in cmd
    assert "--mode" in cmd and "nothinking" in cmd


def test_build_curate_command_api_delegate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_USE_COMPOSE_RUN", "1")
    monkeypatch.setattr("joryu.jobs.runner.resolve_docker_bin", lambda: "/usr/bin/docker")
    host_root = Path("C:/repo")
    monkeypatch.setattr("joryu.jobs.runner.resolve_host_repo_root", lambda _root: host_root)
    (tmp_path / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    spec = CurateJobSpec(skip_llm=True)
    job_id = "abc-123"
    cmd = build_curate_command(tmp_path, spec, job_id=job_id)
    assert cmd[0:3] == ["/usr/bin/docker", "run", "--rm"]
    assert "joryu.cli.curate" in cmd
    assert "--skip-llm" in cmd
    assert "--dst" in cmd
    assert cmd[cmd.index("--dst") + 1] == curate_job_dst_rel(job_id)


def test_build_curate_command_injects_job_dst_via_build_job_command(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("JORYU_USE_COMPOSE_RUN", "1")
    monkeypatch.setattr("joryu.jobs.runner.resolve_docker_bin", lambda: "/usr/bin/docker")
    host_root = Path("C:/repo")
    monkeypatch.setattr("joryu.jobs.runner.resolve_host_repo_root", lambda _root: host_root)
    (tmp_path / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    record = JobRecord.create(CurateJobSpec(skip_llm=True))
    cmd = build_job_command(tmp_path, record)
    assert "--dst" in cmd
    assert cmd[cmd.index("--dst") + 1] == curate_job_dst_rel(record.id)


def test_should_use_compose_run_env(monkeypatch) -> None:
    monkeypatch.delenv("JORYU_USE_COMPOSE_RUN", raising=False)
    monkeypatch.setattr("joryu.jobs.runner.platform.system", lambda: "Linux")
    monkeypatch.setattr("joryu.jobs.runner.Path.exists", lambda _self: False)
    assert should_use_compose_run(env={"JORYU_USE_COMPOSE_RUN": "true"}) is False
    assert should_use_api_docker_delegate(env={"JORYU_USE_COMPOSE_RUN": "true"}) is True


def test_resolve_docker_bin_missing(monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.shutil.which", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="docker CLI not found"):
        resolve_docker_bin()


def test_runner_executes_queued_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    store = JobStore(tmp_path)
    spec = DistillJobSpec(count=1)
    record = JobRecord.create(spec)
    store.save(record)

    calls: list[list[str]] = []
    stats_called: list[DistillJobSpec] = []

    def fake_run(cmd, _cwd, log_path, _on_process):
        calls.append(cmd)
        log_path.write_text("ok\n", encoding="utf-8")
        return 0

    def fake_stats(s: DistillJobSpec) -> int:
        stats_called.append(s)
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=fake_stats,
        command_builder=lambda _root, record: [
            "fake-distill",
            *record.spec.to_distill_argv(),  # type: ignore[union-attr]
        ],
    )
    runner.enqueue(record)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        loaded = store.load(record.id)
        if loaded.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
        time.sleep(0.05)

    loaded = store.load(record.id)
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.exit_code == 0
    assert calls
    assert stats_called[-1] == spec


def test_runner_distill_fails_when_vllm_probe_preflight_fails(tmp_path: Path, monkeypatch) -> None:
    from joryu.preflight import PreflightError

    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)

    def fail_probe(*_args, **_kwargs) -> None:
        raise PreflightError("probe failed")

    monkeypatch.setattr("joryu.preflight.ensure_vllm_limits", fail_probe)

    store = JobStore(tmp_path)
    spec = DistillJobSpec(count=1)
    record = JobRecord.create(spec)
    store.save(record)

    calls: list[list[str]] = []

    def fake_run(cmd, _cwd, log_path, _on_process):
        calls.append(cmd)
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, rec: ["fake-distill"],
    )
    runner.enqueue(record)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        loaded = store.load(record.id)
        if loaded.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
        time.sleep(0.05)

    loaded = store.load(record.id)
    assert loaded.status == JobStatus.FAILED
    assert loaded.error == "probe failed"
    assert calls == []
    assert "probe failed" in store.log_path(record.id).read_text(encoding="utf-8")


def test_runner_executes_curate_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    store = JobStore(tmp_path)
    spec = CurateJobSpec(skip_llm=True)
    record = JobRecord.create(spec)
    store.save(record)

    calls: list[list[str]] = []

    def fake_run(cmd, _cwd, log_path, _on_process):
        calls.append(cmd)
        log_path.write_text("ok\n", encoding="utf-8")
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, rec: ["fake-curate", *rec.spec.to_curate_argv()],  # type: ignore[union-attr]
    )
    runner.enqueue(record)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        loaded = store.load(record.id)
        if loaded.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
        time.sleep(0.05)

    loaded = store.load(record.id)
    assert loaded.kind == JobKind.CURATE
    assert loaded.status == JobStatus.SUCCEEDED
    assert calls == [["fake-curate", "--skip-llm"]]


def test_runner_serializes_two_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    first = JobRecord.create(DistillJobSpec(count=1))
    second = JobRecord.create(DistillJobSpec(count=2))
    store.save(first)
    store.save(second)

    concurrent = 0
    max_concurrent = 0
    finished: list[str] = []

    def fake_run(cmd, _cwd, log_path, _on_process):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.1)
        concurrent -= 1
        idx = cmd.index("--count")
        finished.append(cmd[idx + 1])
        log_path.write_text("done\n", encoding="utf-8")
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, record: [
            "fake-distill",
            *record.spec.to_distill_argv(),  # type: ignore[union-attr]
        ],
    )
    runner.enqueue(first)
    runner.enqueue(second)

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if len(finished) >= 2:
            break
        time.sleep(0.05)

    assert max_concurrent == 1
    assert set(finished) == {"1", "2"}
    assert store.load(first.id).status == JobStatus.SUCCEEDED
    assert store.load(second.id).status == JobStatus.SUCCEEDED


def test_make_refresh_stats_uses_repo_root_paths(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "dashboard" / "public"
    out_dir.mkdir(parents=True)
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_stats_main(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("joryu.cli.stats.main", fake_stats_main)
    spec = DistillJobSpec(config="config.yaml")
    make_refresh_stats(tmp_path)(spec)
    assert calls == [
        [
            "--config",
            str(cfg),
            "--output",
            str(out_dir / "stats.json"),
        ]
    ]


class _FakeProcess:
    """Popen 互換の最小限の偽プロセス。terminate() で wait を解放する。"""

    def __init__(self) -> None:
        self._exit_code: int | None = None
        self._event = threading.Event()
        self.terminate_calls = 0

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self._exit_code is None:
            self._exit_code = -15
            self._event.set()

    def wait_for_terminate(self, timeout: float) -> bool:
        return self._event.wait(timeout)


def test_cancel_queued_job_removes_from_queue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    store = JobStore(tmp_path)
    first = JobRecord.create(DistillJobSpec(count=1))
    second = JobRecord.create(DistillJobSpec(count=2))
    store.save(first)
    store.save(second)

    gate = threading.Event()
    started = threading.Event()
    executed: list[str] = []
    stats_called: list[DistillJobSpec] = []

    def fake_run(cmd, _cwd, log_path, _on_process):
        started.set()
        gate.wait(timeout=5.0)
        executed.append(cmd[cmd.index("--count") + 1])
        log_path.write_text("done\n", encoding="utf-8")
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda s: (stats_called.append(s), 0)[1],
        command_builder=lambda _root, record: [
            "fake-distill",
            *record.spec.to_distill_argv(),  # type: ignore[union-attr]
        ],
    )
    runner.enqueue(first)
    runner.enqueue(second)

    assert started.wait(timeout=5.0)
    assert runner.cancel(second.id) is True
    gate.set()

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if store.load(first.id).status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    assert store.load(first.id).status == JobStatus.SUCCEEDED
    cancelled = store.load(second.id)
    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.error == "cancelled by user"
    assert cancelled.finished_at is not None
    assert executed == ["1"]
    assert stats_called[-1] == first.spec


def test_cancel_running_job_terminates_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    store = JobStore(tmp_path)
    record = JobRecord.create(DistillJobSpec(count=1))
    store.save(record)

    fake_proc = _FakeProcess()
    started = threading.Event()
    stats_called: list[DistillJobSpec] = []

    def fake_run(cmd, _cwd, log_path, on_process):
        if on_process is not None:
            on_process(fake_proc)
        started.set()
        # ブロックしつつ terminate されたら exit code を返す
        fake_proc.wait_for_terminate(timeout=5.0)
        log_path.write_text("partial\n", encoding="utf-8")
        return -15

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda s: (stats_called.append(s), 0)[1],
        command_builder=lambda _root, record: [
            "fake-distill",
            *record.spec.to_distill_argv(),  # type: ignore[union-attr]
        ],
    )
    runner.enqueue(record)

    assert started.wait(timeout=5.0)
    assert runner.cancel(record.id) is True
    assert fake_proc.terminate_calls == 1

    deadline = time.time() + 5.0
    while time.time() < deadline:
        loaded = store.load(record.id)
        if loaded.status in (
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ):
            break
        time.sleep(0.05)

    loaded = store.load(record.id)
    assert loaded.status == JobStatus.CANCELLED
    assert loaded.error == "cancelled by user"
    assert stats_called[-1] == record.spec


def test_cancel_unknown_job_returns_false(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    runner = JobRunner(
        store,
        tmp_path,
        run_command=lambda *args, **kwargs: 0,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, _record: ["noop"],
    )
    assert runner.cancel("does-not-exist") is False


def test_run_subprocess_logged_passes_process_to_callback(tmp_path: Path) -> None:
    """run_subprocess_logged が on_process で Popen を渡し、wait の戻り値を返す。"""

    class _DummyProc:
        def __init__(self) -> None:
            self.stdout = iter(["hello\n", "world\n"])
            self._waited = False

        def wait(self) -> int:
            self._waited = True
            return 0

    captured: list[object] = []

    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _DummyProc()

    from joryu.jobs.runner import run_subprocess_logged

    log = tmp_path / "out.log"
    rc = run_subprocess_logged(
        ["x"],
        cwd=tmp_path,
        log_path=log,
        on_process=lambda p: captured.append(p),
        subprocess_popen=fake_popen,
    )
    assert rc == 0
    assert len(captured) == 1
    text = log.read_text(encoding="utf-8")
    assert "hello" in text and "world" in text


def test_inject_container_name_docker_run() -> None:
    cmd = ["docker", "run", "--rm", "--gpus", "all", "joryu:latest", "python"]
    result = _inject_container_name(cmd, "joryu-job-abc")
    assert result == [
        "docker",
        "run",
        "--rm",
        "--name",
        "joryu-job-abc",
        "--gpus",
        "all",
        "joryu:latest",
        "python",
    ]


def test_inject_container_name_docker_compose_run() -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        "dc.yml",
        "--project-directory",
        "/repo",
        "run",
        "--rm",
        "joryu",
        "joryu-distill",
    ]
    result = _inject_container_name(cmd, "joryu-job-xyz")
    assert result == [
        "docker",
        "compose",
        "-f",
        "dc.yml",
        "--project-directory",
        "/repo",
        "run",
        "--rm",
        "--name",
        "joryu-job-xyz",
        "joryu",
        "joryu-distill",
    ]


def test_inject_container_name_no_rm_unchanged() -> None:
    cmd = ["some", "other", "command"]
    result = _inject_container_name(cmd, "myname")
    assert result == cmd


def test_cancel_running_job_calls_docker_stop(tmp_path: Path, monkeypatch) -> None:
    """実行中ジョブのキャンセル時に docker stop が呼ばれる。"""
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    store = JobStore(tmp_path)
    record = JobRecord.create(DistillJobSpec(count=1))
    store.save(record)

    fake_proc = _FakeProcess()
    started = threading.Event()
    docker_stop_calls: list[list[str]] = []

    def fake_run(cmd, _cwd, log_path, on_process):
        if on_process is not None:
            on_process(fake_proc)
        started.set()
        fake_proc.wait_for_terminate(timeout=5.0)
        log_path.write_text("partial\n", encoding="utf-8")
        return -15

    import subprocess as _subprocess

    original_run = _subprocess.run

    def fake_subprocess_run(cmd, **kwargs):
        if cmd and "stop" in cmd:
            docker_stop_calls.append(list(cmd))
            return type("R", (), {"returncode": 0})()
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("joryu.jobs.runner.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr("joryu.jobs.runner.resolve_docker_bin", lambda: "docker")

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, record: [
            "fake-distill",
            *record.spec.to_distill_argv(),  # type: ignore[union-attr]
        ],
    )
    runner.enqueue(record)

    assert started.wait(timeout=5.0)
    assert runner.cancel(record.id) is True

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if store.load(record.id).status == JobStatus.CANCELLED:
            break
        time.sleep(0.05)

    assert store.load(record.id).status == JobStatus.CANCELLED
    # docker stop が非同期で呼ばれるまで少し待つ
    deadline = time.time() + 2.0
    while time.time() < deadline and not docker_stop_calls:
        time.sleep(0.05)
    assert any("stop" in c for c in docker_stop_calls), (
        f"docker stop not called: {docker_stop_calls}"
    )
    container_name = f"joryu-job-{record.id}"
    assert any(container_name in c for c in docker_stop_calls)


def test_runner_refreshes_curation_during_curate_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 0.05)
    store = JobStore(tmp_path)
    spec = CurateJobSpec(skip_llm=True)
    record = JobRecord.create(spec)
    store.save(record)

    curation_calls: list[tuple[CurateJobSpec, str]] = []
    gate = threading.Event()

    def fake_run(cmd, _cwd, log_path, _on_process):
        gate.wait(timeout=5.0)
        log_path.write_text("ok\n", encoding="utf-8")
        return 0

    def fake_refresh_curation(s: CurateJobSpec, job_id: str) -> int:
        curation_calls.append((s, job_id))
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_curation=fake_refresh_curation,
        command_builder=lambda _root, rec: ["fake-curate", *rec.spec.to_curate_argv()],  # type: ignore[union-attr]
    )
    runner.enqueue(record)

    deadline = time.time() + 5.0
    while time.time() < deadline and len(curation_calls) < 2:
        time.sleep(0.02)

    assert len(curation_calls) >= 2
    gate.set()

    while time.time() < deadline:
        loaded = store.load(record.id)
        if loaded.status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    assert store.load(record.id).status == JobStatus.SUCCEEDED
    assert curation_calls[-1] == (spec, record.id)


def test_runner_ensure_dashboard_data_paths_on_distill_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.STATS_REFRESH_INTERVAL_SEC", 3600.0)
    called: list[Path] = []
    monkeypatch.setattr(
        "joryu.preflight.ensure_dashboard_data_paths",
        lambda root: called.append(root),
    )

    store = JobStore(tmp_path)
    record = JobRecord.create(DistillJobSpec(count=1))
    store.save(record)

    runner = JobRunner(
        store,
        tmp_path,
        run_command=lambda *_args, **_kwargs: 0,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, rec: ["fake-distill"],
    )
    runner.enqueue(record)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if store.load(record.id).status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    assert called == [tmp_path]
