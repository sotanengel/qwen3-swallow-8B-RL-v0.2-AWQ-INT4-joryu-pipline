"""E2E: 「おはよう。今日の東京の天気は？」"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.tools_impl import weather as weather_mod
from tests.conftest import FakeVllmClient
from tests.test_api_chat import STYLES_YAML, TOOLS_YAML, _parse_sse


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
    (tmp_path / "tools.yaml").write_text(
        TOOLS_YAML
        + """
  weather:
    description: Weather lookup
    parameters:
      type: object
      properties:
        location:
          type: string
        date:
          type: string
      required: [location]
""",
        encoding="utf-8",
    )
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"hello"}\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def weather_client(repo_root: Path, monkeypatch):
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr(
        "joryu.datetime_context.now_jst",
        lambda clock=None: fixed,
    )

    weather_call = (
        '<tool_call>{"name":"weather","arguments":'
        '{"location":"東京","date":"2026-06-27"}}</tool_call>'
    )
    app = create_app(repo_root=repo_root)
    app.state.chat_client = FakeVllmClient(
        answers=[weather_call, "今日の東京は晴れで、最高31℃くらいです。"],
        thinking=None,
    )
    return TestClient(app)


@respx.mock
def test_today_tokyo_weather_e2e(weather_client, repo_root, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}]},
        )
    )
    respx.get(weather_mod.FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "weathercode": [1],
                    "temperature_2m_max": [31.0],
                    "temperature_2m_min": [24.0],
                    "precipitation_probability_max": [20],
                }
            },
        )
    )

    created = weather_client.post("/api/chat/sessions").json()
    session_id = created["session_id"]

    with weather_client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "おはよう。今日の東京の天気は？"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [t for t, _ in events]
    assert types[-1] == "done"
    for style_id in ("prose", "qa_short", "dialog", "report"):
        assert types.count("column_done") >= 1
        col_done = [d for t, d in events if t == "column_done" and d.get("column") == style_id]
        assert len(col_done) == 1, f"missing column_done for {style_id}"

    tool_calls = [d for t, d in events if t == "tool_call"]
    assert tool_calls, "expected at least one tool_call event"
    weather_calls = [tc for tc in tool_calls if tc.get("name") == "weather"]
    assert weather_calls, "expected weather tool_call"
    args = weather_calls[0]["arguments"]
    assert "東京" in json.dumps(args, ensure_ascii=False)
    assert "2026" in json.dumps(args, ensure_ascii=False)

    report_tokens = [
        d.get("delta", "") for t, d in events if t == "token" and d.get("column") == "report"
    ]
    report_text = "".join(report_tokens)
    assert report_text.strip(), "report column should have non-empty assistant text"

    out_path = repo_root / "data" / "distilled" / "responses.jsonl"
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 4
