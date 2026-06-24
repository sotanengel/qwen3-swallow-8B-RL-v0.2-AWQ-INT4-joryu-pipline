"""API 検索エンドポイントのテスト。"""

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
search:
  index_dir: data/distilled/.search_index
  top_k_default: 50
  snippet_chars: 200
""".strip(),
        encoding="utf-8",
    )
    jsonl_dir = tmp_path / "data" / "distilled"
    jsonl_dir.mkdir(parents=True)
    records = [
        {
            "prompt": "桜の特徴",
            "answer": "春に咲く美しい花",
            "mode": "thinking",
            "category": "国語",
        },
        {"prompt": "1+1", "answer": "2", "mode": "nothinking", "category": "数学"},
    ]
    (jsonl_dir / "responses.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    return TestClient(create_app(repo_root=repo_root))


def test_search_status(client: TestClient) -> None:
    res = client.get("/api/dashboard/search/status")
    assert res.status_code == 200
    data = res.json()
    assert "index_status" in data
    assert "record_count" in data


def test_search_post_returns_ranked_hits(client: TestClient) -> None:
    res = client.post(
        "/api/dashboard/search",
        json={"query": "桜", "mode": "all", "category": "", "limit": 10, "offset": 0},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["index_status"] in ("ready", "empty")
    assert data["total"] >= 1
    hit = data["hits"][0]
    assert "record_key" in hit
    assert "score" in hit
    assert "snippet" in hit
    assert hit["record"]["prompt"] == "桜の特徴"


def test_search_post_filters_mode(client: TestClient) -> None:
    res = client.post(
        "/api/dashboard/search",
        json={"query": "", "mode": "nothinking", "category": "", "limit": 10, "offset": 0},
    )
    assert res.status_code == 200
    hits = res.json()["hits"]
    assert all(h["record"].get("mode") == "nothinking" for h in hits)


def test_search_post_empty_query_lists_all(client: TestClient) -> None:
    res = client.post(
        "/api/dashboard/search",
        json={"query": "", "mode": "all", "category": "", "limit": 10, "offset": 0},
    )
    assert res.status_code == 200
    assert res.json()["total"] == 2
