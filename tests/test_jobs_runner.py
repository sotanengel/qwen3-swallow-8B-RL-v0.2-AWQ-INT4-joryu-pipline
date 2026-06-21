"""jobs/runner.py のユニットテスト。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from joryu.jobs.models import DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.runner import (
    JobRunner,
    build_job_command,
    resolve_docker_bin,
    should_use_compose_run,
)
from joryu.jobs.store import JobStore


def test_build_job_command_compose(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_USE_COMPOSE_RUN", "1")
    monkeypatch.setattr("joryu.jobs.runner.resolve_docker_bin", lambda: "/usr/bin/docker")
    host_root = tmp_path.resolve()
    monkeypatch.setattr("joryu.jobs.runner.resolve_host_repo_root", lambda _root: host_root)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    spec = DistillJobSpec(count=3, mode="nothinking")
    cmd = build_job_command(tmp_path, spec)
    assert cmd[0:8] == [
        "/usr/bin/docker",
        "compose",
        "-f",
        str(host_root / "docker-compose.yml"),
        "--project-directory",
        str(host_root),
        "run",
        "--rm",
    ]
    assert "joryu-distill" in cmd
    assert "--count" in cmd and "3" in cmd
    assert "--mode" in cmd and "nothinking" in cmd


def test_should_use_compose_run_env(monkeypatch) -> None:
    monkeypatch.delenv("JORYU_USE_COMPOSE_RUN", raising=False)
    monkeypatch.setattr("joryu.jobs.runner.platform.system", lambda: "Linux")
    monkeypatch.setattr("joryu.jobs.runner.Path.exists", lambda _self: False)
    assert should_use_compose_run(env={"JORYU_USE_COMPOSE_RUN": "true"}) is True


def test_resolve_docker_bin_missing(monkeypatch) -> None:
    monkeypatch.setattr("joryu.jobs.runner.shutil.which", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="docker CLI not found"):
        resolve_docker_bin()


def test_runner_executes_queued_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    spec = DistillJobSpec(count=1)
    record = JobRecord.create(spec)
    store.save(record)

    calls: list[list[str]] = []
    stats_called: list[DistillJobSpec] = []

    def fake_run(cmd: list[str], _cwd: Path, log_path: Path) -> int:
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
        command_builder=lambda _root, spec: ["fake-distill", *spec.to_distill_argv()],
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
    assert stats_called == [spec]


def test_runner_serializes_two_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    first = JobRecord.create(DistillJobSpec(count=1))
    second = JobRecord.create(DistillJobSpec(count=2))
    store.save(first)
    store.save(second)

    concurrent = 0
    max_concurrent = 0
    finished: list[str] = []

    def fake_run(cmd: list[str], _cwd: Path, log_path: Path) -> int:
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
        command_builder=lambda _root, spec: ["fake-distill", *spec.to_distill_argv()],
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
