"""Think タグ answer 残留防止 (#295 / Epic #294 Sub#1)。"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from joryu.chat.session import ChatColumn, ChatSession, ChatSessionConfig, ChatSessionState
from joryu.chat.streamer import stream_column_turn
from joryu.chat.thinking_guard import strip_think_blocks
from joryu.chat.tool_loop import ToolLoopRunner
from joryu.chat.turn_persistence import TurnPersistence
from joryu.styles import StylePreset
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolUpstreamError
from joryu.vllm_client import ChatResult
from tests.conftest import FakeVllmClient

REPO_ROOT = Path(__file__).resolve().parents[2]

_WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Weather lookup",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]

_THINK_LEAK = (
    "<think>\nWe need to answer user query about today's Tokyo weather.\n"
    "The previous tool call returned error.\n"
)


def test_strip_think_blocks_removes_paired_block() -> None:
    raw = f"{_THINK_LEAK}</think>\n今日は晴れです。"
    assert strip_think_blocks(raw) == "今日は晴れです。"


def test_strip_think_blocks_removes_orphan_open_tag() -> None:
    assert strip_think_blocks(_THINK_LEAK) == ""


def test_strip_think_blocks_removes_orphan_close_tag() -> None:
    assert strip_think_blocks("</think>今日は晴れ。") == "今日は晴れ。"


def _make_dialog_session(tmp_path: Path) -> ChatSession:
    preset = StylePreset(style_id="dialog", label="対話", instruction="2〜4文で。")
    col = ChatColumn(style_id="dialog", label="対話")
    config = ChatSessionConfig(
        base_system_prompt="base",
        model_name="test-model",
        config_hash="hash",
        tools=_WEATHER_TOOLS,
        tool_ids=("weather",),
        tool_definitions=(
            {
                "name": "weather",
                "description": "Weather lookup",
                "parameters": _WEATHER_TOOLS[0]["function"]["parameters"],
            },
        ),
        out_path=tmp_path / "out.jsonl",
        style_presets={"dialog": preset},
    )
    state = ChatSessionState(
        session_id="sess-1",
        columns={"dialog": col},
        created_at=0.0,
        last_updated_at=0.0,
    )
    return ChatSession(config=config, state=state)


class _UpstreamErrorExecutor:
    def run(self, call: ParsedToolCall) -> str:
        raise ToolUpstreamError(status=400, body='{"missing":["location"]}', url="http://x")


async def _persist_column(tmp_path: Path, answers: list[str]) -> dict:
    TurnPersistence.reset_dedup()
    session = _make_dialog_session(tmp_path)
    column = session.columns["dialog"]
    client = FakeVllmClient(answers=answers, thinking=None)

    async for _event in stream_column_turn(
        session,
        column,
        "今日の東京の天気は？",
        client=client,
        executor=_UpstreamErrorExecutor(),
        sampling={"temperature": 0.7, "top_p": 0.9},
    ):
        pass

    line = tmp_path.joinpath("out.jsonl").read_text(encoding="utf-8").strip()
    return json.loads(line)


def test_persisted_answer_excludes_think_after_tool_error_recovery(tmp_path: Path) -> None:
    weather_call = '<tool_call>{"name":"weather","arguments":{"location":"東京"}}</tool_call>'
    leaked = f"{_THINK_LEAK}</think>\n天気は晴れです。"
    record = asyncio.run(
        _persist_column(
            tmp_path,
            [weather_call, leaked],
        )
    )
    answer = record["answer"]
    assert "<think>" not in answer
    assert "</think>" not in answer
    assert "天気は晴れ" in answer


def test_tool_loop_final_answer_excludes_orphan_think_block() -> None:
    async def _collect() -> ChatResult | None:
        runner = ToolLoopRunner(max_turns=1)
        final_chat: ChatResult | None = None
        async for event in runner.run(
            column_id="dialog",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=None,
            executor=None,
            client=FakeVllmClient(answers=[_THINK_LEAK], thinking=None),
            stream_client=None,
            sampling={"temperature": 0.7},
        ):
            if event.get("type") == "_tool_loop_done":
                final_chat = event["final_chat"]
        return final_chat

    final_chat = asyncio.run(_collect())
    assert final_chat is not None
    assert "<think>" not in (final_chat.answer or "")
    assert "Tokyo weather" not in (final_chat.answer or "")


def test_persisted_answer_excludes_paired_think_block(tmp_path: Path) -> None:
    paired = f"{_THINK_LEAK}</think>\n今日は晴れです。"
    record = asyncio.run(_persist_column(tmp_path, [paired]))
    answer = record["answer"]
    assert "<think>" not in answer
    assert answer == "今日は晴れです。"


def test_turn_persistence_sanitizes_answer_directly(tmp_path: Path) -> None:
    session = _make_dialog_session(tmp_path)
    chat = ChatResult(
        thinking=None,
        answer=f"{_THINK_LEAK}</think>\nOK",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
    )
    record, _rec_id = TurnPersistence().persist_turn(
        session=session,
        style_id="dialog",
        system_prompt="sys",
        user_text="q",
        turn_index=0,
        final_chat=chat,
        turns=[],
        sampling={},
    )
    assert record is not None
    assert record["answer"] == "OK"


def test_lint_jsonl_rejects_think_tags_in_answer(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps({"prompt": "p", "answer": _THINK_LEAK}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "lint_jsonl.py"), str(bad)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 1
    assert "answer must not contain" in rc.stderr
