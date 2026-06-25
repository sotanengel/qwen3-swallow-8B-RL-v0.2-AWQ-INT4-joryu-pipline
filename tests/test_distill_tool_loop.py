"""distill tool loop integration tests."""

from __future__ import annotations

from pathlib import Path

from joryu.config import Config
from joryu.distill import run_distill
from joryu.tool_executor import StubToolExecutor
from tests.helpers.jsonl import read_jsonl, write_jsonl

from .conftest import FakeVllmClient


def _write_bank(path: Path, rows: list[dict]) -> None:
    write_jsonl(path, rows)


def test_tool_loop_false_keeps_turns_empty(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1", "tool_ids": ["search"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    tool_call = '<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>'
    client = FakeVllmClient(answer=tool_call, thinking=None)
    run_distill(cfg, bank_path=bank, out_path=out, client=client, tool_loop=False)
    rec = read_jsonl(out)[0]
    assert rec["turns"] == []
    assert len(client.calls) == 1


def test_tool_loop_two_turns_with_stub(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "計算して", "tool_ids": ["calc"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    turn1 = '<tool_call>{"name":"calc","arguments":{"expression":"2+3"}}</tool_call>'
    turn2 = "答えは 5 です。"
    client = FakeVllmClient(answers=[turn1, turn2], thinking=None)
    executor = StubToolExecutor({"calc": "5"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
    )
    assert len(client.calls) == 2
    rec = read_jsonl(out)[0]
    assert len(rec["turns"]) >= 2
    assert rec["turns"][0]["tool_calls"][0]["name"] == "calc"
    assert rec["turns"][1]["role"] == "tool"
    assert rec["answer"] == "答えは 5 です。"


def test_tool_loop_exhausted_finish_reason(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P", "tool_ids": ["search"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    cfg.distill.tool_loop_max_turns = 1
    tool_call = '<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>'
    client = FakeVllmClient(answer=tool_call, thinking=None)
    executor = StubToolExecutor({"search": "ok"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
        tool_loop_max_turns=1,
    )
    rec = read_jsonl(out)[0]
    assert rec["finish_reason"] == "tool_loop_exhausted"


def test_no_tool_call_ends_immediately(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    client = FakeVllmClient(answer="直接回答", thinking=None)
    run_distill(cfg, bank_path=bank, out_path=out, client=client, tool_loop=True)
    rec = read_jsonl(out)[0]
    assert len(rec["turns"]) == 1
    assert rec["turns"][0]["role"] == "assistant"
    assert rec["turns"][0]["tool_calls"] == []
    assert len(client.calls) == 1


def test_tool_loop_second_call_uses_qwen3_message_format(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "計算", "tool_ids": ["calc"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    turn1 = '<tool_call>{"name":"calc","arguments":{"expression":"2+3"}}</tool_call>'
    client = FakeVllmClient(answers=[turn1, "答えは 5 です。"], thinking=None)
    executor = StubToolExecutor({"calc": "5"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
    )
    second_msgs = client.calls[1]["messages"]
    assert second_msgs[0]["role"] == "system"
    assert second_msgs[1]["role"] == "user"
    assistant_msgs = [m for m in second_msgs if m.get("role") == "assistant"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert len(assistant_msgs) == 1
    tool_turn_assistant = assistant_msgs[0]
    assert "tool_calls" in tool_turn_assistant
    assert tool_turn_assistant["tool_calls"][0]["function"]["name"] == "calc"
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["name"] == "calc"
    assert tool_msgs[0]["content"] == "5"


def test_tool_loop_multiple_tool_calls_one_assistant_message(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "調べて計算", "tool_ids": ["search", "calc"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    turn1 = (
        '<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>'
        '<tool_call>{"name":"calc","arguments":{"expression":"1+1"}}</tool_call>'
    )
    client = FakeVllmClient(answers=[turn1, "完了"], thinking=None)
    executor = StubToolExecutor({"search": "ok", "calc": "2"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
    )
    second_msgs = client.calls[1]["messages"]
    assistant_with_tools = [
        m for m in second_msgs if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_with_tools) == 1
    assert len(assistant_with_tools[0]["tool_calls"]) == 2
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert {m["name"] for m in tool_msgs} == {"search", "calc"}
