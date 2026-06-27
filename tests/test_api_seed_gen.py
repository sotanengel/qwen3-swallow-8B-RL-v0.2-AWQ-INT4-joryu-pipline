"""API seed-gen endpoints."""

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
    repo = Path(__file__).resolve().parents[1]
    domains_src = repo / "src/joryu/seed_gen/domains.yaml"
    (tmp_path / "src/joryu/seed_gen").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/joryu/seed_gen/domains.yaml").write_text(
        domains_src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bank = tmp_path / "data/prompts/training_prompts.jsonl"
    bank.parent.mkdir(parents=True)
    bank.write_text('{"prompt":"legacy","category":"数学・論理・抽象思考"}\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    return TestClient(create_app(repo_root=repo_root))


def test_seed_gen_options(client: TestClient) -> None:
    resp = client.get("/api/seed-gen/jobs/options")
    assert resp.status_code == 200
    assert "defaults" in resp.json()


def test_seed_gen_status(client: TestClient) -> None:
    resp = client.get("/api/seed-gen/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bank_total"] == 1
    assert len(body["domains"]) == 15


def test_create_seed_gen_job_fake(client: TestClient) -> None:
    resp = client.post(
        "/api/seed-gen/jobs",
        json={"fake_llm": True, "dry_run": True, "target_total": 50, "domain": "math"},
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "seed_gen"


def test_manual_append_prompt(client: TestClient) -> None:
    resp = client.post(
        "/api/seed-gen/prompts",
        json={"prompt": "手動追加テスト", "domain": "math"},
    )
    assert resp.status_code == 200
    assert resp.json()["domain"] == "math"
