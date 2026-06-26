"""API チャットエンドポイントのテスト (#148)。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.jobs.models import DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.runner import JobRunner
from joryu.styles import StylePreset

TOOLS_YAML = """
tools:
  search:
    description: Web search
    parameters:
      type: object
      properties:
        query:
          type: string
      required: [query]
""".strip()

STYLES_YAML = """
styles:
  prose:
    label: 散文
    instruction: 散文で。
  qa_short:
    label: 短答
    instruction: 短く。
  dialog:
    label: 対話
    instruction: 対話で。
  report:
    label: レポート
    instruction: レポートで。
""".strip()


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
  tools_file: tools.yaml
  system_prompt: test system
export:
  out_dir: exports
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "styles.yaml").write_text(STYLES_YAML, encoding="utf-8")
    (tmp_path / "tools.yaml").write_text(TOOLS_YAML, encoding="utf-8")
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"hello"}\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    app = create_app(repo_root=repo_root)
    return TestClient(app)


def test_list_styles(client: TestClient) -> None:
    resp = client.get("/api/chat/styles")
    assert resp.status_code == 200
    styles = resp.json()
    assert len(styles) == 4
    ids = {s["style_id"] for s in styles}
    assert ids == {"prose", "qa_short", "dialog", "report"}
    prose = next(s for s in styles if s["style_id"] == "prose")
    assert prose["label"] == "散文"


def test_create_session(client: TestClient) -> None:
    resp = client.post("/api/chat/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert len(body["columns"]) == 4
    col_ids = {c["style_id"] for c in body["columns"]}
    assert col_ids == {"prose", "qa_short", "dialog", "report"}
    for col in body["columns"]:
        assert col["turn_index"] == 0
        assert col["messages"] == []


def test_get_session(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    resp = client.get(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert len(body["columns"]) == 4


def test_get_missing_session(client: TestClient) -> None:
    resp = client.get("/api/chat/sessions/does-not-exist")
    assert resp.status_code == 404


def test_delete_session(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    resp = client.delete(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404


def test_delete_missing_session(client: TestClient) -> None:
    resp = client.delete("/api/chat/sessions/does-not-exist")
    assert resp.status_code == 404


def test_session_ttl_expiry(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    store = client.app.state.chat_sessions
    session = store.get(session_id)
    assert session is not None
    session.expires_at = time.monotonic() - 1
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404


def test_probe_idle_returns_ok(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle_ok"


def test_probe_rejects_when_running_id_set(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    runner: JobRunner = client.app.state.job_runner
    with runner._lock:
        runner._running_id = "busy-job-id"
    try:
        resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
        assert resp.status_code == 409
        body = resp.json()
        assert body["detail"]["error"] == "job_active"
        assert body["detail"]["running_id"] == "busy-job-id"
    finally:
        with runner._lock:
            runner._running_id = None


def test_probe_rejects_when_queued_job_exists(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    store = client.app.state.job_store
    record = JobRecord.create(DistillJobSpec(count=1))
    record.status = JobStatus.QUEUED
    store.save(record)
    resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "job_active"


def test_purge_expired_on_create(client: TestClient) -> None:
    store = client.app.state.chat_sessions
    styles = {"prose": StylePreset(style_id="prose", label="散文", instruction="散文で。")}
    old = store.create(styles)
    old.expires_at = time.monotonic() - 1
    store._sessions[old.session_id] = old
    client.post("/api/chat/sessions")
    assert store.get(old.session_id) is None
