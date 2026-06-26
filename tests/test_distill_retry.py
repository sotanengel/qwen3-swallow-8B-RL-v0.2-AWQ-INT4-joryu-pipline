"""distill_retry.py: 打ち切り検出時の同一条件再試行。"""

from __future__ import annotations

import time
from typing import Any

from joryu.distill_retry import TRUNCATION_RETRY_ALERT_THRESHOLD, generate_until_complete
from joryu.vllm_client import ChatResult


class _SequenceClient:
    def __init__(self, responses: list[tuple[str, str | None]]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        **sampling_overrides: Any,
    ) -> ChatResult:
        idx = len(self.calls)
        self.calls.append({"messages": messages, "sampling": dict(sampling_overrides)})
        answer, finish_reason = self._responses[min(idx, len(self._responses) - 1)]
        return ChatResult(
            thinking=None,
            answer=answer,
            finish_reason=finish_reason,
            prompt_tokens=1,
            completion_tokens=1,
        )


def _build_record(chat: ChatResult) -> dict[str, Any]:
    return {
        "prompt": "P",
        "answer": (chat.answer or "").strip(),
        "finish_reason": chat.finish_reason,
        "sampling": {},
    }


def test_generate_until_complete_retries_on_truncation() -> None:
    client = _SequenceClient(
        [
            ("途中\n\n## 1. 章", "length"),
            ("完結した回答。", "stop"),
        ]
    )
    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={},
        build_record=_build_record,
    )
    assert len(client.calls) == 2
    assert attempts == 2
    assert record is not None
    assert record["answer"] == "完結した回答。"
    assert record["generation_attempts"] == 2


def test_generate_until_complete_returns_none_when_deadline_exceeded() -> None:
    client = _SequenceClient([("途中\n\n## 1. 章", "length")])
    tick = {"now": 100.0}

    def time_fn() -> float:
        return tick["now"]

    def sleep_fn(_sec: float) -> None:
        tick["now"] += 1.0

    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={},
        build_record=_build_record,
        deadline=101.0,
        min_interval_sec=1.0,
        time_fn=time_fn,
        sleep_fn=sleep_fn,
    )
    assert record is None
    assert attempts == 1
    assert len(client.calls) == 1


def test_generate_until_complete_calls_on_retry_at_threshold() -> None:
    client = _SequenceClient(
        [
            ("a\n\n## h", "length"),
            ("b\n\n## h", "length"),
            ("c\n\n## h", "length"),
            ("完結。", "stop"),
        ]
    )
    alerts: list[tuple[int, dict[str, Any]]] = []

    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={},
        build_record=_build_record,
        on_retry=lambda attempt, rec: alerts.append((attempt, rec)),
    )
    assert record is not None
    assert attempts == 4
    assert len(alerts) == 1
    assert alerts[0][0] == TRUNCATION_RETRY_ALERT_THRESHOLD


def test_generate_until_complete_skips_when_deadline_already_past() -> None:
    client = _SequenceClient([("完結。", "stop")])
    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={},
        build_record=_build_record,
        deadline=time.time() - 1,
    )
    assert record is None
    assert attempts == 0
    assert len(client.calls) == 0


def test_generate_until_complete_bumps_max_tokens_on_length() -> None:
    client = _SequenceClient(
        [
            ("cut", "length"),
            ("完結した回答。", "stop"),
        ]
    )
    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={"max_tokens": 2048},
        build_record=_build_record,
        max_tokens_cap=3584,
    )
    assert record is not None
    assert attempts == 2
    assert client.calls[0]["sampling"]["max_tokens"] == 2048
    assert client.calls[1]["sampling"]["max_tokens"] == 3072


def test_generate_until_complete_clamps_max_tokens_at_cap() -> None:
    client = _SequenceClient(
        [
            ("cut", "length"),
            ("cut", "length"),
            ("完結した回答。", "stop"),
        ]
    )
    generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={"max_tokens": 3000},
        build_record=_build_record,
        max_tokens_cap=3584,
    )
    assert client.calls[1]["sampling"]["max_tokens"] == 3584


def test_generate_until_complete_does_not_bump_on_heuristic_truncation() -> None:
    # finish_reason=stop は record_looks_truncated で即 non-truncated 扱いのため None を使う
    client = _SequenceClient(
        [
            ("途中\n\n## 1. 章", None),
            ("完結した回答。", "stop"),
        ]
    )
    generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={"max_tokens": 2048},
        build_record=_build_record,
        max_tokens_cap=3584,
    )
    assert client.calls[0]["sampling"]["max_tokens"] == 2048
    assert client.calls[1]["sampling"]["max_tokens"] == 2048


def test_generate_until_complete_caps_attempts_and_accepts_last() -> None:
    client = _SequenceClient([("cut", "length")] * 12)
    record, attempts = generate_until_complete(
        client=client,
        messages=[{"role": "user", "content": "P"}],
        tools=None,
        sampling={"max_tokens": 2048},
        build_record=_build_record,
        max_tokens_cap=3584,
        max_attempts=10,
    )
    assert record is not None
    assert attempts == 10
    assert len(client.calls) == 10
    assert record["truncation_retry_capped"] is True
    assert record["generation_attempts"] == 10
    assert record["finish_reason"] == "length"
