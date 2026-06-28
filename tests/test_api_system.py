"""GET /api/system/models テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.orchestrator.profile import ModelProfile
from joryu.orchestrator.service import ModelOrchestrator


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("JORYU_ORCHESTRATOR_BACKEND", "fake")
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
""".strip(),
        encoding="utf-8",
    )
    app = create_app(repo_root=tmp_path)
    orch: ModelOrchestrator = app.state.orchestrator
    orch.ensure_profile(ModelProfile.DISTILL)
    return TestClient(app)


def test_get_models_snapshot(client: TestClient) -> None:
    resp = client.get("/api/system/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["active"] == "distill"
    assert any(p["name"] == "seed_gen" for p in data["profiles"])


def test_live_screening_not_found(client: TestClient) -> None:
    resp = client.get("/api/live/screening")
    assert resp.status_code == 404
