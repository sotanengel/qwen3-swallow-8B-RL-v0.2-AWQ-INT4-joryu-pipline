"""API ジョブエンドポイントのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app

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
  calc:
    description: Calculator
    parameters:
      type: object
      properties:
        expression:
          type: string
      required: [expression]
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
  system_prompt: test
export:
  out_dir: exports
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "styles.yaml").write_text(
        """
styles:
  polite:
    label: 丁寧語
    instruction: 丁寧に。
""".strip(),
        encoding="utf-8",
    )
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


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_job_options(client: TestClient) -> None:
    resp = client.get("/api/jobs/options")
    assert resp.status_code == 200
    body = resp.json()
    assert "polite" in {s["id"] for s in body["styles"]}
    assert body["defaults"]["mode"] == "thinking"
    assert "auto" in body["modes"]
    tool_ids = {t["id"] for t in body["tools"]}
    assert "search" in tool_ids
    assert "calc" in tool_ids


def test_create_job_with_tool_ids(client: TestClient) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "count": 1,
            "tool_ids": ["search", "calc"],
            "tool_loop": True,
            "max_turns": 3,
        },
    )
    assert resp.status_code == 201
    spec = resp.json()["spec"]
    assert spec["tool_ids"] == ["search", "calc"]
    assert spec["tool_loop"] is True
    assert spec["max_turns"] == 3


def test_create_and_list_jobs(client: TestClient, repo_root: Path) -> None:
    resp = client.post("/api/jobs", json={"count": 2, "style": ["polite"]})
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "queued"
    assert job["kind"] == "distill"
    assert job["spec"]["count"] == 2

    listed = client.get("/api/jobs").json()
    assert len(listed) == 1
    assert listed[0]["id"] == job["id"]

    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["id"] == job["id"]

    logs = client.get(f"/api/jobs/{job['id']}/logs").json()
    assert "offset" in logs


def test_create_job_validation_error(client: TestClient) -> None:
    resp = client.post("/api/jobs", json={"count": -1})
    assert resp.status_code == 400


def test_get_missing_job(client: TestClient) -> None:
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_cancel_missing_job_returns_404(client: TestClient) -> None:
    resp = client.post("/api/jobs/does-not-exist/cancel")
    assert resp.status_code == 404


def test_cancel_queued_job_via_api(client: TestClient) -> None:
    """API 経由でキュー中ジョブをキャンセルできる。"""
    from joryu.jobs.models import DistillJobSpec, JobRecord
    from joryu.jobs.runner import JobRunner

    runner: JobRunner = client.app.state.job_runner
    store = client.app.state.job_store

    # ランナーが実際の docker を呼ばないように差し替え
    runner._command_builder = lambda _root, record: [
        "noop",
        *record.spec.to_distill_argv(),  # type: ignore[union-attr]
    ]
    runner._run_command = lambda *args, **kwargs: 0  # type: ignore[assignment]

    # キュー先頭を埋めるためにダミーをセットしてから 2 件目を入れる
    busy = JobRecord.create(DistillJobSpec(count=1))
    store.save(busy)
    with runner._lock:
        runner._running_id = busy.id  # 実行中扱いで block

    pending = JobRecord.create(DistillJobSpec(count=2))
    store.save(pending)
    runner.enqueue(pending)

    resp = client.post(f"/api/jobs/{pending.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # 後片付け
    with runner._lock:
        runner._running_id = None
