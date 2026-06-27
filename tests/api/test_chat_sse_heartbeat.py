"""SSE heartbeat and disconnect tests (#204)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from joryu.chat import sse as sse_mod
from joryu.chat.service import ChatService
from joryu.chat.session import ChatSessionStore
from joryu.tool_calls import ParsedToolCall
from tests.conftest import FakeVllmClient
from tests.test_api_chat import STYLES_YAML, TOOLS_YAML

WEATHER_TOOLS_YAML = (
    TOOLS_YAML
    + """
  calc:
    description: Calculator
    parameters:
      type: object
      properties:
        expression:
          type: string
      required: [expression]
  weather:
    description: Weather lookup
    parameters:
      type: object
      properties:
        location:
          type: string
      required: [location]
"""
)


class _SlowExecutor:
    def run(self, call: ParsedToolCall) -> str:
        time.sleep(3.5)
        return f"slow:{call.name}"


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


def test_sse_service_emits_heartbeats_during_slow_tool(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse_mod, "HEARTBEAT_INTERVAL_SEC", 1.0)
    calc_call = '<tool_call>{"name":"calc","arguments":{"expression":"2+2"}}</tool_call>'
    chat_client = FakeVllmClient(
        answers=[calc_call, "答えは 4 です。"],
        thinking=None,
    )
    executor = _SlowExecutor()
    service = ChatService(
        repo_root=repo_root,
        session_store=ChatSessionStore(),
        chat_client=chat_client,
        executor=executor,
    )
    session = service.create_session(service.load_styles())

    async def _collect() -> str:
        parts: list[str] = []
        async for chunk in service.stream_single_column(
            session,
            session.columns["prose"].style_id,
            "今日の東京の天気は？",
        ):
            parts.append(chunk)
        return "".join(parts)

    body = asyncio.run(_collect())
    assert "tool_call" in body
    assert body.count(": ping") >= 2


def test_with_heartbeat_emits_comments_during_idle() -> None:
    async def _collect() -> list[str]:
        async def slow_stream():
            await asyncio.sleep(2.5)
            yield "event: done\ndata: {}\n\n"

        parts: list[str] = []
        async for chunk in sse_mod.with_heartbeat(slow_stream(), interval=0.5):
            parts.append(chunk)
        return parts

    parts = asyncio.run(_collect())
    ping_count = sum(1 for part in parts if ": ping" in part)
    assert ping_count >= 2


def test_monitor_client_disconnect_sets_cancel_event() -> None:
    cancel_event = asyncio.Event()

    class _FakeRequest:
        def __init__(self) -> None:
            self._calls = 0

        async def is_disconnected(self) -> bool:
            self._calls += 1
            return self._calls >= 2

    asyncio.run(
        sse_mod.monitor_client_disconnect(_FakeRequest(), cancel_event, poll_interval=0.01),
    )
    assert cancel_event.is_set()
