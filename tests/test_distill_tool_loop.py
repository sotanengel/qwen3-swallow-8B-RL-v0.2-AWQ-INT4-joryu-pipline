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


def test_tool_loop_aggregates_tool_calls_on_record(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "計算して", "tool_ids": ["calc"]}])
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
    rec = read_jsonl(out)[0]
    assert len(rec["tool_calls"]) == 1
    assert rec["tool_calls"][0]["name"] == "calc"


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


def test_tool_loop_second_call_uses_openai_message_format(tmp_path: Path) -> None:
    """vllm serve は assistant.tool_calls[].{id,type=function} と tool.tool_call_id を要求する。"""
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
    tc = tool_turn_assistant["tool_calls"][0]
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "calc"
    assert isinstance(tc.get("id"), str) and tc["id"].startswith("call_")
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["name"] == "calc"
    assert tool_msgs[0]["content"] == "5"
    assert tool_msgs[0]["tool_call_id"] == tc["id"]


def test_tool_loop_runs_bare_json_tool_call(tmp_path: Path) -> None:
    """#103: bare JSON 形式の tool_call でも tool_loop が executor を呼んで2 turn 目に進む。"""
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "計算して", "tool_ids": ["calc"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    bare = '{"name":"calc","arguments":{"expression":"2+3"}}'
    client = FakeVllmClient(answers=[bare, "答えは 5 です。"], thinking=None)
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
    assert len(rec["tool_calls"]) == 1
    assert rec["tool_calls"][0]["name"] == "calc"
    # turns: assistant(bare JSON tool_call) -> tool result -> assistant final
    assert len(rec["turns"]) >= 2
    assert rec["turns"][0]["tool_calls"][0]["name"] == "calc"
    assert rec["turns"][1]["role"] == "tool"
    assert rec["turns"][1]["content"] == "5"
    assert rec["answer"] == "答えは 5 です。"


def test_tool_loop_turn_persists_raw_completion(tmp_path: Path) -> None:
    """#103: tool_loop 中の各 assistant turn にも raw_completion が残る。"""
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "計算", "tool_ids": ["calc"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    bare = '{"name":"calc","arguments":{"expression":"2+3"}}'
    client = FakeVllmClient(answers=[bare, "答えは 5 です。"], thinking=None)
    executor = StubToolExecutor({"calc": "5"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
    )
    rec = read_jsonl(out)[0]
    assistant_turns = [t for t in rec["turns"] if t["role"] == "assistant"]
    assert len(assistant_turns) >= 2
    for turn in assistant_turns:
        assert "raw_completion" in turn


def test_tool_loop_skips_empty_tool_call_tag(tmp_path: Path) -> None:
    """空 <tool_call>{}</tool_call> は tool_call として扱わずループを終了する。"""
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P", "tool_ids": ["search"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    turn1 = "<tool_call>{}</tool_call>\nあとがき"
    client = FakeVllmClient(answer=turn1, thinking=None)
    executor = StubToolExecutor({"search": "ok"})
    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        executor=executor,
        tool_loop=True,
    )
    assert len(client.calls) == 1
    rec = read_jsonl(out)[0]
    assert rec["tool_calls"] == []
    assert rec["turns"][0]["tool_calls"] == []
    assert rec["answer"] == "あとがき"


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
    tool_calls = assistant_with_tools[0]["tool_calls"]
    assert len(tool_calls) == 2
    for tc in tool_calls:
        assert tc["type"] == "function"
        assert isinstance(tc["id"], str) and tc["id"].startswith("call_")
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert {m["name"] for m in tool_msgs} == {"search", "calc"}
    expected_ids = {tc["id"] for tc in tool_calls}
    assert {m["tool_call_id"] for m in tool_msgs} == expected_ids
