"""API ダッシュボードライブデータエンドポイントのテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(
        """
distill:
  out_dir: data/distilled
  out_file: responses.jsonl
""".strip(),
        encoding="utf-8",
    )
    public = tmp_path / "dashboard" / "public"
    public.mkdir(parents=True)
    stats = {
        "total": 2,
        "models": {"M": 2},
        "modes": {},
        "categories": {},
        "styles": {},
        "answer_length": {"count": 2, "mean": 10, "max": 20, "min": 5, "bins": []},
        "thinking_length": {"count": 0, "mean": 0, "max": 0, "min": 0, "bins": []},
        "sampling": {"temperature": {}, "top_p": {}},
        "timeline_daily": {},
        "_meta": {"generated_at": "2026-01-01T00:00:00+00:00"},
    }
    (public / "stats.json").write_text(json.dumps(stats), encoding="utf-8")

    jsonl_dir = tmp_path / "data" / "distilled"
    jsonl_dir.mkdir(parents=True)
    (jsonl_dir / "responses.jsonl").write_text(
        '{"prompt":"P1","answer":"A1"}\n{"prompt":"P2","answer":"A2"}\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    return TestClient(create_app(repo_root=repo_root))


def test_dashboard_stats_returns_live_json(client: TestClient) -> None:
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    assert res.headers.get("cache-control", "").startswith("no-store")
    data = res.json()
    assert data["total"] == 2
    assert data["_meta"]["generated_at"] == "2026-01-01T00:00:00+00:00"


def test_dashboard_stats_empty_when_missing(client: TestClient, repo_root: Path) -> None:
    (repo_root / "dashboard" / "public" / "stats.json").unlink()
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_dashboard_responses_returns_jsonl_text(client: TestClient) -> None:
    res = client.get("/api/dashboard/responses")
    assert res.status_code == 200
    assert res.headers.get("cache-control", "").startswith("no-store")
    assert "P1" in res.text
    assert "P2" in res.text


def test_dashboard_delete_one_response(client: TestClient, repo_root: Path) -> None:
    from joryu.responses_store import record_id

    rid = record_id({"prompt": "P1", "answer": "A1"})
    res = client.delete(f"/api/dashboard/responses/{rid}")
    assert res.status_code == 200
    body = res.json()
    assert body["deleted"] == 1
    assert body["remaining"] == 1

    get_res = client.get("/api/dashboard/responses")
    assert "P1" not in get_res.text
    assert "P2" in get_res.text

    stats = client.get("/api/dashboard/stats").json()
    assert stats["total"] == 1


def test_dashboard_delete_one_not_found(client: TestClient) -> None:
    res = client.delete("/api/dashboard/responses/nonexistent")
    assert res.status_code == 404


def test_dashboard_delete_all_responses(client: TestClient, repo_root: Path) -> None:
    res = client.delete("/api/dashboard/responses")
    assert res.status_code == 200
    body = res.json()
    assert body["deleted"] == 2
    assert body["remaining"] == 0

    get_res = client.get("/api/dashboard/responses")
    assert get_res.text.strip() == ""

    stats = client.get("/api/dashboard/stats").json()
    assert stats["total"] == 0
