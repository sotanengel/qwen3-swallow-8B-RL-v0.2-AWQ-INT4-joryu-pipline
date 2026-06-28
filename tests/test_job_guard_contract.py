"""A-5: 単一 GPU 排他契約テスト。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.jobs.models import DistillJobSpec, JobRecord, JobStatus
from joryu.jobs.runner import JobRunner
from joryu.jobs.store import JobStore
from tests.conftest import FakeVllmClient


@pytest.fixture(autouse=True)
def _skip_vllm_probe_in_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("joryu.preflight.ensure_vllm_limits", lambda *_args, **_kwargs: None)


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
    (tmp_path / "styles.yaml").write_text(
        """
styles:
  prose:
    label: 散文
    instruction: 散文で。
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"hello"}\n',
        encoding="utf-8",
    )
    return tmp_path


def test_only_one_job_runs_at_a_time(tmp_path: Path) -> None:
    """2 本 enqueue → 同時 RUNNING は 1 本のみ (JobRunner 契約)。"""
    store = JobStore(tmp_path)
    first = JobRecord.create(DistillJobSpec(count=1))
    second = JobRecord.create(DistillJobSpec(count=2))
    store.save(first)
    store.save(second)

    concurrent = 0
    max_concurrent = 0

    def fake_run(cmd, _cwd, log_path, _on_process):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
        concurrent -= 1
        log_path.write_text("done\n", encoding="utf-8")
        return 0

    runner = JobRunner(
        store,
        tmp_path,
        run_command=fake_run,
        refresh_stats=lambda _s: 0,
        command_builder=lambda _root, record: ["fake", "--count", str(record.spec.count)],  # type: ignore[union-attr]
    )
    runner.enqueue(first)
    runner.enqueue(second)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if (
            store.load(first.id).status == JobStatus.SUCCEEDED
            and store.load(second.id).status == JobStatus.SUCCEEDED
        ):
            break
        time.sleep(0.05)

    assert max_concurrent == 1
    assert store.load(first.id).status == JobStatus.SUCCEEDED
    assert store.load(second.id).status == JobStatus.SUCCEEDED


def test_chat_blocked_during_running_job(repo_root: Path) -> None:
    """ジョブ実行中に distill 以外が active → chat 409 wrong_profile。"""
    from joryu.orchestrator.profile import ModelProfile
    from joryu.orchestrator.state import OrchestratorState, OrchestratorStatus

    app = create_app(repo_root=repo_root)
    app.state.chat_client = FakeVllmClient(answer="ok", thinking=None)
    client = TestClient(app)

    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]

    runner: JobRunner = app.state.job_runner
    orch = app.state.orchestrator
    with runner._lock:
        runner._running_id = "busy-job"
    orch._save_state(
        OrchestratorState(status=OrchestratorStatus.ACTIVE, active=ModelProfile.SEED_GEN)
    )
    try:
        resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "wrong_profile"
    finally:
        with runner._lock:
            runner._running_id = None
        orch.init_distill_active()

    resp = client.post(f"/api/chat/sessions/{session_id}/_probe")
    assert resp.status_code == 200
