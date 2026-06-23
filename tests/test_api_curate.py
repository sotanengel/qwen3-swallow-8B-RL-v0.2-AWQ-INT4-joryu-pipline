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


def test_create_curate_job_without_vllm(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("joryu.api.routes.curate.joryu_container_running", lambda **_: False)
    resp = client.post("/api/curate/jobs", json={"skip_llm": False})
    assert resp.status_code == 400

    resp = client.post("/api/curate/jobs", json={"skip_llm": True})
    assert resp.status_code == 201
    job = resp.json()
    assert job["kind"] == "curate"
    assert job["spec"]["skip_llm"] is True


def test_list_curate_jobs(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("joryu.api.routes.curate.joryu_container_running", lambda **_: False)
    created = client.post("/api/curate/jobs", json={"skip_llm": True}).json()
    listed = client.get("/api/curate/jobs").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_curate_job_logs_and_cancel(client: TestClient, monkeypatch) -> None:
    from joryu.jobs.runner import JobRunner

    monkeypatch.setattr("joryu.api.routes.curate.joryu_container_running", lambda **_: False)
    resp = client.post("/api/curate/jobs", json={"skip_llm": True})
    job_id = resp.json()["id"]

    runner: JobRunner = client.app.state.job_runner
    runner._command_builder = lambda _root, record: ["noop"]
    runner._run_command = lambda *args, **kwargs: 0  # type: ignore[assignment]

    with runner._lock:
        runner._running_id = job_id

    cancel = client.post(f"/api/curate/jobs/{job_id}/cancel")
    assert cancel.status_code == 200

    logs = client.get(f"/api/curate/jobs/{job_id}/logs").json()
    assert "offset" in logs

    with runner._lock:
        runner._running_id = None
