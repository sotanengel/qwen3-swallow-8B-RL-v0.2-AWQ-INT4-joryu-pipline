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


def test_create_curate_job_enqueues_while_other_profile_starting(client: TestClient) -> None:
    """別プロファイル (distill) 起動中でも curate ジョブは enqueue される (409 で弾かない)。

    JobRunner が profile を screening に自動切替して実行するため、API 層で
    profile_starting 409 を返すのは誤り。
    """
    from joryu.orchestrator.profile import ModelProfile
    from joryu.orchestrator.state import OrchestratorState, OrchestratorStatus

    orch = client.app.state.orchestrator
    orch._save_state(
        OrchestratorState(status=OrchestratorStatus.STARTING, target=ModelProfile.DISTILL)
    )

    resp = client.post("/api/curate/jobs", json={"skip_llm": False})
    assert resp.status_code == 201, resp.text


def test_create_curate_job_enqueues_while_profile_switching(client: TestClient) -> None:
    """profile 切替中でも curate ジョブは enqueue される。"""
    from joryu.orchestrator.profile import ModelProfile
    from joryu.orchestrator.state import OrchestratorState, OrchestratorStatus

    orch = client.app.state.orchestrator
    orch._save_state(
        OrchestratorState(status=OrchestratorStatus.SWITCHING, target=ModelProfile.DISTILL)
    )

    resp = client.post("/api/curate/jobs", json={"skip_llm": False})
    assert resp.status_code == 201, resp.text


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
