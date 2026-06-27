"""Chat session management E2E (#227)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.conftest import FakeVllmClient
from tests.test_api_chat import STYLES_YAML, TOOLS_YAML

from joryu.api.app import create_app
from joryu.chat.session import ChatSessionStore

pytestmark = [pytest.mark.e2e_chat, pytest.mark.timeout(15)]


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


def test_session_persists_after_store_reopen(client: TestClient) -> None:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    db_path = client.app.state.chat_sessions._db._db_path
    store2 = ChatSessionStore(db_path=db_path)
    loaded = store2.get(session_id)
    assert loaded is not None
    assert loaded.session_id == session_id


def test_three_sessions_listed_in_updated_order(client: TestClient) -> None:
    ids = [client.post("/api/chat/sessions").json()["session_id"] for _ in range(3)]
    listed = client.get("/api/chat/sessions").json()
    assert len(listed["items"]) == 3
    listed_ids = [item["session_id"] for item in listed["items"]]
    assert set(listed_ids) == set(ids)
    updates = [item["last_updated_at"] for item in listed["items"]]
    assert updates == sorted(updates, reverse=True)


def test_title_after_first_message_and_patch(client: TestClient) -> None:
    session_id = client.post("/api/chat/sessions").json()["session_id"]
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "first message title"},
    ) as resp:
        resp.read()
    listed = client.get("/api/chat/sessions").json()
    item = next(i for i in listed["items"] if i["session_id"] == session_id)
    assert item["title"] == "first message title"

    client.patch(
        f"/api/chat/sessions/{session_id}",
        json={"title": "renamed"},
    )
    listed2 = client.get("/api/chat/sessions").json()
    item2 = next(i for i in listed2["items"] if i["session_id"] == session_id)
    assert item2["title"] == "renamed"


def test_delete_removes_from_list(client: TestClient) -> None:
    session_id = client.post("/api/chat/sessions").json()["session_id"]
    client.delete(f"/api/chat/sessions/{session_id}")
    listed = client.get("/api/chat/sessions").json()
    assert all(i["session_id"] != session_id for i in listed["items"])
