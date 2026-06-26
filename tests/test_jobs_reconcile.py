"""API 起動時の stale ジョブ記録リコンサイル (#A-2)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.jobs.models import CurateJobSpec, DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore


@pytest.fixture
def jobs_store(tmp_path: Path) -> JobStore:
    jobs_dir = tmp_path / "data" / "jobs"
    jobs_dir.mkdir(parents=True)
    return JobStore(jobs_dir)


@pytest.fixture
def runner(jobs_store: JobStore, tmp_path: Path) -> JobRunner:
    return JobRunner(jobs_store, tmp_path)


def test_reconcile_stale_running_job(jobs_store: JobStore, runner: JobRunner) -> None:
    record = JobRecord.create(DistillJobSpec(count=1))
    record.status = JobStatus.RUNNING
    jobs_store.save(record)

    count = runner.reconcile_stale_jobs()

    assert count == 1
    updated = jobs_store.load(record.id)
    assert updated.status == JobStatus.FAILED
    assert updated.error == "recovered on api start"
    assert updated.finished_at is not None


def test_reconcile_stale_queued_job(jobs_store: JobStore, runner: JobRunner) -> None:
    record = JobRecord.create(CurateJobSpec(skip_llm=True))
    record.status = JobStatus.QUEUED
    jobs_store.save(record)

    count = runner.reconcile_stale_jobs()

    assert count == 1
    updated = jobs_store.load(record.id)
    assert updated.status == JobStatus.FAILED
    assert updated.error == "recovered on api start"


def test_reconcile_leaves_terminal_jobs_unchanged(jobs_store: JobStore, runner: JobRunner) -> None:
    for status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        record = JobRecord.create(DistillJobSpec(count=1))
        record.status = status
        record.finished_at = "2020-01-01T00:00:00+00:00"
        jobs_store.save(record)

    count = runner.reconcile_stale_jobs()

    assert count == 0


def test_reconcile_does_not_populate_queue(jobs_store: JobStore, runner: JobRunner) -> None:
    record = JobRecord.create(DistillJobSpec(count=1))
    record.status = JobStatus.QUEUED
    jobs_store.save(record)

    runner.reconcile_stale_jobs()

    assert runner.running_id is None
    with runner._lock:
        assert runner._queue == []
