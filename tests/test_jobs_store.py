"""jobs/store.py のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.jobs.models import DistillJobSpec, JobKind, JobRecord, JobStatus
from joryu.jobs.store import JobStore


def test_save_load_roundtrip(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    spec = DistillJobSpec(count=5, duration="30m", style=["prose"])
    record = JobRecord.create(spec)
    store.save(record)

    loaded = store.load(record.id)
    assert loaded.id == record.id
    assert loaded.spec.count == 5
    assert loaded.spec.style == ["prose"]
    assert loaded.status == JobStatus.QUEUED


def test_list_all_newest_first(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    older = JobRecord(
        id="older",
        kind=JobKind.DISTILL,
        spec=DistillJobSpec(),
        status=JobStatus.SUCCEEDED,
        created_at="2020-01-01T00:00:00+00:00",
    )
    newer = JobRecord(
        id="newer",
        kind=JobKind.DISTILL,
        spec=DistillJobSpec(),
        status=JobStatus.QUEUED,
        created_at="2025-01-01T00:00:00+00:00",
    )
    store.save(older)
    store.save(newer)

    ids = [r.id for r in store.list_all()]
    assert ids == ["newer", "older"]


def test_read_log_offset(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    store.append_log("job-1", "line1\n")
    store.append_log("job-1", "line2\n")

    chunk, end = store.read_log("job-1")
    assert chunk == "line1\nline2\n"
    assert end == len(chunk)

    tail, new_end = store.read_log("job-1", offset=end)
    assert tail == ""
    assert new_end == end


def test_load_missing_raises(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("missing")
