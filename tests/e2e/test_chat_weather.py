"""E2E: 天気質問フリーズ回帰 (#207)。"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from tests.conftest import FakeVllmClient
from tests.test_api_chat import STYLES_YAML, TOOLS_YAML, _parse_sse

from joryu.api.app import create_app
from joryu.tool_executor import McpToolExecutor
from joryu.tools_impl import weather as weather_mod

pytestmark = [pytest.mark.e2e_chat, pytest.mark.timeout(15)]

WEATHER_TOOLS_YAML = (
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
"""
)

WEATHER_CALL = (
    '<tool_call>{"name":"weather","arguments":{"location":"東京","date":"2026-06-27"}}</tool_call>'
)


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
  tools_file: tools.yaml
  system_prompt: test system
mcp:
  enabled: false
  url: "http://localhost:8200"
tools:
  weather:
    timeout: 5.0
    provider: open_meteo
export:
  out_dir: exports
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "styles.yaml").write_text(STYLES_YAML, encoding="utf-8")
    (tmp_path / "tools.yaml").write_text(WEATHER_TOOLS_YAML, encoding="utf-8")
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"hello"}\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fixed_jst(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2026, 6, 27, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setattr("joryu.datetime_context.now_jst", lambda clock=None: fixed)
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "stub")


def _make_client(repo_root: Path, *, answers: list[str] | None = None) -> TestClient:
    app = create_app(repo_root=repo_root)
    app.state.chat_client = FakeVllmClient(
        answers=answers or [WEATHER_CALL, "今日の東京は晴れです。"],
        thinking=None,
    )
    app.state.mcp_runtime = type(app.state.mcp_runtime)(enabled=False, state="down")
    return TestClient(app)


def _stream_weather_prompt(client: TestClient) -> tuple[list[tuple[str, dict]], float]:
    created = client.post("/api/chat/sessions").json()
    session_id = created["session_id"]
    started = time.monotonic()
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"prompt": "今日の東京の天気は？"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")
    elapsed = time.monotonic() - started
    return _parse_sse(body), elapsed


def _mock_open_meteo_success() -> None:
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


@respx.mock
def test_e2e_chat_weather_success(repo_root: Path, fixed_jst: None) -> None:
    _mock_open_meteo_success()
    client = _make_client(repo_root)
    events, elapsed = _stream_weather_prompt(client)
    assert elapsed < 15.0
    types = [t for t, _ in events]
    assert types[-1] == "done"
    assert any(t == "tool_call" for t in types)
    assert not any(t == "tool_error" for t in types)


@respx.mock
def test_e2e_chat_weather_timeout_emits_tool_error(
    repo_root: Path,
    fixed_jst: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JORYU_WEATHER_TIMEOUT", "0.001")
    weather_mod._geocode_location.cache_clear()
    respx.get(weather_mod.GEOCODING_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    client = _make_client(repo_root)
    events, elapsed = _stream_weather_prompt(client)
    assert elapsed < 15.0
    types = [t for t, _ in events]
    assert types[-1] == "done"
    assert "tool_error" in types


@respx.mock
def test_e2e_chat_weather_5xx_emits_tool_error(repo_root: Path, fixed_jst: None) -> None:
    respx.get(weather_mod.GEOCODING_URL).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"name": "東京", "latitude": 35.68, "longitude": 139.76}]},
        )
    )
    respx.get(weather_mod.FORECAST_URL).mock(return_value=httpx.Response(503))
    client = _make_client(repo_root)
    events, elapsed = _stream_weather_prompt(client)
    assert elapsed < 15.0
    types = [t for t, _ in events]
    assert types[-1] == "done"
    assert "tool_error" in types


@respx.mock
def test_e2e_chat_weather_mcp_fallback(repo_root: Path, fixed_jst: None) -> None:
    cfg = (
        (repo_root / "config.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "enabled: false",
            "enabled: true",
        )
    )
    (repo_root / "config.yaml").write_text(cfg, encoding="utf-8")
    respx.get("http://localhost:8200/health").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    respx.post("http://localhost:8200/tools/weather").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    _mock_open_meteo_success()
    app = create_app(repo_root=repo_root)
    app.state.chat_client = FakeVllmClient(
        answers=[WEATHER_CALL, "今日の東京は晴れです。"],
        thinking=None,
    )
    app.state.chat_executor = McpToolExecutor(
        url="http://localhost:8200",
        connect_timeout=0.5,
        read_timeout=0.5,
    )
    client = TestClient(app)
    events, elapsed = _stream_weather_prompt(client)
    assert elapsed < 15.0
    types = [t for t, _ in events]
    assert types[-1] == "done"
    assert any(t == "tool_result" for t in types)
    tool_results = [d for t, d in events if t == "tool_result"]
    assert any("東京" in (r.get("content") or "") for r in tool_results)
