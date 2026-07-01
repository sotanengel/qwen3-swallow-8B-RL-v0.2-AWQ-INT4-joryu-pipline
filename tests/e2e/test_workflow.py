"""ブラウザ完結 LLM ワークフロー e2e (FakeBackend)。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.jobs.models import JobStatus
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore


@pytest.fixture(autouse=True)
def _skip_vllm_probe_in_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("joryu.preflight.ensure_vllm_limits", lambda *_args, **_kwargs: None)


@pytest.fixture
def workflow_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, JobRunner]:
    monkeypatch.setenv("JORYU_ORCHESTRATOR_BACKEND", "fake")
    monkeypatch.setenv("JORYU_USE_COMPOSE_RUN", "1")
    (tmp_path / "config.yaml").write_text(
        """
model:
  name: test
distill:
  prompt_bank: data/prompts/training_prompts.jsonl
  out_dir: data/distilled
  out_file: responses.jsonl
  styles_file: styles.yaml
  system_prompt: test
export:
  out_dir: exports
models:
  auto_restore: distill
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "styles.yaml").write_text("styles: {}\n", encoding="utf-8")
    (tmp_path / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"p","style":"prose"}\n',
        encoding="utf-8",
    )

    app = create_app(repo_root=tmp_path)
    runner: JobRunner = app.state.job_runner

    def _instant_ok(
        cmd: list[str],
        _cwd: Path,
        log_path: Path,
        _on_process: object,
    ) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("[fake-job] ok\n", encoding="utf-8")
        return 0

    runner._run_command = _instant_ok  # noqa: SLF001
    return TestClient(app), runner


def _snapshot(client: TestClient) -> dict[str, object]:
    resp = client.get("/api/system/models")
    assert resp.status_code == 200
    return resp.json()


def test_full_browser_workflow_profile_transitions(
    workflow_client: tuple[TestClient, JobRunner],
) -> None:
    client, runner = workflow_client
    store: JobStore = client.app.state.job_store  # type: ignore[attr-defined]

    snap = _snapshot(client)
    assert snap["status"] in ("stopped", "active")

    # 1. distill
    r1 = client.post("/api/jobs", json={"count": 1})
    assert r1.status_code == 201
    job1 = r1.json()["id"]
    for _ in range(100):
        time.sleep(0.02)
        try:
            rec = store.load(job1)
        except FileNotFoundError:
            continue
        if rec.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
    assert store.load(job1).status == JobStatus.SUCCEEDED
    assert _snapshot(client)["active"] == "distill"

    # 2. seed_gen (profile switch)
    r2 = client.post("/api/seed-gen/jobs", json={"mode": "create", "target_total": 1})
    assert r2.status_code == 201
    job2 = r2.json()["id"]
    for _ in range(100):
        time.sleep(0.02)
        try:
            rec = store.load(job2)
        except FileNotFoundError:
            continue
        if rec.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
    assert store.load(job2).status == JobStatus.SUCCEEDED
    assert _snapshot(client)["active"] == "distill"

    # 3. screening curate
    r3 = client.post(
        "/api/curate/jobs",
        json={"screening": True, "prompt_bank": True, "skip_llm": True},
    )
    assert r3.status_code == 201
    job3 = r3.json()["id"]
    for _ in range(100):
        time.sleep(0.02)
        try:
            rec = store.load(job3)
        except FileNotFoundError:
            continue
        if rec.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
    assert store.load(job3).status == JobStatus.SUCCEEDED

    # 4. re-distill
    r4 = client.post("/api/jobs", json={"count": 1})
    assert r4.status_code == 201
    job4 = r4.json()["id"]
    for _ in range(100):
        time.sleep(0.02)
        try:
            rec = store.load(job4)
        except FileNotFoundError:
            continue
        if rec.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            break
    assert store.load(job4).status == JobStatus.SUCCEEDED
    assert _snapshot(client)["active"] == "distill"
