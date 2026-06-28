"""API curation ジョブエンドポイントのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(
        """
model:
  name: test-model
  mode: thinking
distill:
  prompt_bank: data/prompts/training_prompts.jsonl
  out_dir: data/distilled
  out_file: responses.jsonl
  styles_file: styles.yaml
  system_prompt: test
export:
  out_dir: exports
curate:
  out_dir: data/curated
""".strip(),
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"hello","answer":"world"}\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    app = create_app(repo_root=repo_root)
    return TestClient(app)


def test_curate_options(client: TestClient) -> None:
    resp = client.get("/api/curate/jobs/options")
    assert resp.status_code == 200
    body = resp.json()
    assert body["input_ready"] is True
    assert "defaults" in body


def test_create_curate_job_without_vllm(client: TestClient) -> None:
    resp = client.post("/api/curate/jobs", json={"skip_llm": False})
    assert resp.status_code == 201

    resp = client.post("/api/curate/jobs", json={"skip_llm": True})
    assert resp.status_code == 201
    job = resp.json()
    assert job["kind"] == "curate"
    assert job["spec"]["skip_llm"] is True


def test_create_screening_prompt_bank_job(client: TestClient, repo_root: Path) -> None:
    bank = repo_root / "data" / "prompts" / "training_prompts.jsonl"
    bank.parent.mkdir(parents=True)
    bank.write_text('{"prompt":"テスト質問","domain":"general_qa"}\n', encoding="utf-8")

    resp = client.post(
        "/api/curate/jobs",
        json={
            "screening": True,
            "prompt_bank": True,
            "skip_llm": True,
            "src": "data/prompts/training_prompts.jsonl",
        },
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["spec"]["screening"] is True
    assert job["spec"]["prompt_bank"] is True
    assert job["spec"]["src"] == "data/prompts/training_prompts.jsonl"


def test_list_curate_jobs(client: TestClient) -> None:
    created = client.post("/api/curate/jobs", json={"skip_llm": True}).json()
    listed = client.get("/api/curate/jobs").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_curate_job_logs_and_cancel(client: TestClient) -> None:
    from joryu.jobs.models import CurateJobSpec, JobRecord
    from joryu.jobs.runner import JobRunner

    runner: JobRunner = client.app.state.job_runner
    store = client.app.state.job_store

    runner._command_builder = lambda _root, record: ["noop"]
    runner._run_command = lambda *args, **kwargs: 0  # type: ignore[assignment]

    busy = JobRecord.create(CurateJobSpec(skip_llm=True))
    store.save(busy)
    with runner._lock:
        runner._running_id = busy.id

    pending = JobRecord.create(CurateJobSpec(skip_llm=True))
    store.save(pending)
    runner.enqueue(pending)

    cancel = client.post(f"/api/curate/jobs/{pending.id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    with runner._lock:
        runner._running_id = None
