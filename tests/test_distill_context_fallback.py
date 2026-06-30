"""蒸留: コンテキスト超過時のツール無効リトライ。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from joryu.config import Config
from joryu.distill import run_distill
from joryu.vllm.protocol import VllmError
from tests.helpers.jsonl import read_jsonl, write_jsonl

from .conftest import FakeVllmClient

_OVERFLOW_DETAIL = (
    "vLLM daemon HTTP 400: "
    '{"error":{"message":"This model\'s maximum context length is 4096 tokens. '
    "However, you requested 2048 output tokens and your prompt contains 875414 characters "
    "(more than 262144 characters, which is the upper bound for 2048 input tokens). "
    "Please reduce the length of the input prompt or the number of requested output tokens. "
    '(parameter=input_text, value=875414)","type":"BadRequestError","code":400}}'
)


class _OverflowThenOkClient(FakeVllmClient):
    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        if tools:
            self.calls.append(
                {
                    "messages": messages,
                    "enable_thinking": kwargs.get("enable_thinking", True),
                    "tools": tools,
                    "tool_choice": kwargs.get("tool_choice"),
                    "sampling": {k: v for k, v in kwargs.items()},
                }
            )
            raise VllmError(_OVERFLOW_DETAIL)
        return super().chat_via_template(messages, tools=tools, **kwargs)


def test_distill_retries_without_tools_on_context_overflow(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    write_jsonl(bank, [{"prompt": "再犯率について論じて", "tool_ids": ["search"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True
    client = _OverflowThenOkClient(answer="刑事司法の課題を論じます。", thinking=None)
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        tool_loop=True,
    )
    assert n == 1
    rec = read_jsonl(out)[0]
    assert rec["answer"] == "刑事司法の課題を論じます。"
    assert rec["tools_disabled_retry"] is True
    assert len(client.calls) == 2
    assert client.calls[0]["tools"] is not None
    assert client.calls[1]["tools"] is None


def test_distill_skips_when_tools_disabled_retry_also_fails(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    write_jsonl(bank, [{"prompt": "P", "tool_ids": ["search"]}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.distill.tool_loop = True

    class _AlwaysOverflowClient(FakeVllmClient):
        def chat_via_template(self, messages, *, tools=None, **kwargs):
            self.calls.append(
                {
                    "messages": messages,
                    "tools": tools,
                    "sampling": dict(kwargs),
                }
            )
            raise VllmError(_OVERFLOW_DETAIL)

    client = _AlwaysOverflowClient(answer="x")
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        tool_loop=True,
    )
    assert n == 0
    assert not out.exists() or read_jsonl(out) == []
    assert len(client.calls) == 2
