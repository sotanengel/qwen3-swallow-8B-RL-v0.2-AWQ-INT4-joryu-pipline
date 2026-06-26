"""API チャットエンドポイントのテスト (#148)。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.jobs.models import DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.runner import JobRunner
from joryu.styles import StylePreset
from tests.conftest import FakeVllmClient

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
    app.state.chat_client = FakeVllmClient(answer="テスト応答", thinking=None)
    return TestClient(app)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_type = ""
        data_line = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_line = line[6:]
        if event_type and data_line:
            events.append((event_type, json.loads(data_line)))
    return events


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
    session.state.expires_at = time.monotonic() - 1
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


def test_probe_allows_when_queued_job_exists_in_store_only(client: TestClient) -> None:
    """store に QUEUED のみ (runner idle) なら probe は 200。"""
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    store = client.app.state.job_store
    record = JobRecord.create(DistillJobSpec(count=1))
    record.status = JobStatus.QUEUED
    store.save(record)
    resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle_ok"


def test_probe_ok_with_stale_running_record_after_reconcile(
    repo_root: Path,
) -> None:
    """stale RUNNING 記録 → create_app (reconcile) → probe 200。"""
    from joryu.jobs.store import JobStore

    jobs_dir = repo_root / "data" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    record = JobRecord.create(DistillJobSpec(count=1))
    record.status = JobStatus.RUNNING
    JobStore(jobs_dir).save(record)

    app = create_app(repo_root=repo_root)
    app.state.chat_client = FakeVllmClient(answer="テスト応答", thinking=None)
    client = TestClient(app)

    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle_ok"

    reconciled = app.state.job_store.load(record.id)
    assert reconciled.status == JobStatus.FAILED
    assert reconciled.error == "recovered on api start"


def test_purge_expired_on_create(client: TestClient) -> None:
    store = client.app.state.chat_sessions
    styles = {"prose": StylePreset(style_id="prose", label="散文", instruction="散文で。")}
    from joryu.tool_executor import StubToolExecutor

    old = store.create(
        styles,
        base_system_prompt="base",
        model_name="m",
        config_hash="h",
        tools=[],
        tool_ids=[],
        out_path=client.app.state.repo_root / "data" / "distilled" / "responses.jsonl",
        executor=StubToolExecutor(),
    )
    old.state.expires_at = time.monotonic() - 1
    store._sessions[old.session_id] = old
    client.post("/api/chat/sessions")
    assert store.get(old.session_id) is None


def test_sse_initial_broadcast(client: TestClient, repo_root: Path) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "hello"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    types = [t for t, _ in events]
    assert "column_start" in types
    assert "turn_start" in types
    assert types.index("column_start") < types.index("token")
    assert "token" in types
    assert "column_done" in types
    assert types[-1] == "done"
    out_path = repo_root / "data" / "distilled" / "responses.jsonl"
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 4
    for line in lines:
        rec = json.loads(line)
        assert rec["category"] == "人間との対話"
        assert rec["session_id"] == session_id


def test_sse_column_message(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "first"},
    ) as resp:
        resp.read()
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/columns/prose/messages",
        json={"prompt": "second"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    assert events[-1][0] == "done"
    session = client.get(f"/api/chat/sessions/{session_id}").json()
    prose = next(c for c in session["columns"] if c["style_id"] == "prose")
    assert prose["turn_index"] == 2


def test_initial_broadcast_rejects_after_first_turn(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "first"},
    ) as resp:
        resp.read()
    resp = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "again"},
    )
    assert resp.status_code == 400


def test_messages_reject_when_job_active(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    runner: JobRunner = client.app.state.job_runner
    with runner._lock:
        runner._running_id = "busy"
    try:
        resp = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"prompt": "hi"},
        )
        assert resp.status_code == 409
    finally:
        with runner._lock:
            runner._running_id = None
