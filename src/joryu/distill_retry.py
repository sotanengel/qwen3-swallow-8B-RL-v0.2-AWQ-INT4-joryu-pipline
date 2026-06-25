"""蒸留生成の打ち切り検出と同一条件再試行。"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

from joryu.truncation import record_looks_truncated
from joryu.vllm_client import ChatResult, SupportsChat

TRUNCATION_RETRY_ALERT_THRESHOLD = 3


def generate_until_complete(
    *,
    client: SupportsChat,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None,
    sampling: dict[str, Any],
    build_record: Callable[[ChatResult], dict[str, Any]],
    chat_fn: Callable[..., ChatResult] | None = None,
    deadline: float | None = None,
    min_interval_sec: float = 0.0,
    on_retry: Callable[[int, dict[str, Any]], None] | None = None,
    log: Callable[..., Any] | None = None,
    time_fn: Callable[[], float] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> tuple[dict[str, Any] | None, int]:
    """打ち切りでないレコードが得られるまで同一条件で再生成する。

    Qwen3 thinking モード固定で動作する (#94 で nothinking/auto 削除済み)。
    deadline 到達時にまだ打ち切りの場合は (None, attempts) を返す。
    """
    now_fn = time_fn or time.time
    pause_fn = sleep_fn or time.sleep
    emit = log if log is not None else lambda *_a, **_k: None
    attempts = 0

    while True:
        if deadline is not None and now_fn() >= deadline:
            return None, attempts

        attempts += 1
        if chat_fn is None:
            chat = client.chat_via_template(
                messages,
                enable_thinking=True,
                tools=tools,
                **sampling,
            )
        else:
            chat = chat_fn(
                messages,
                tools=tools,
                **sampling,
            )
        record = build_record(chat)
        if not record_looks_truncated(record):
            record["generation_attempts"] = attempts
            return record, attempts

        if on_retry is not None and attempts >= TRUNCATION_RETRY_ALERT_THRESHOLD:
            on_retry(attempts, record)

        emit(
            f"[joryu-distill] 打ち切り検出 (attempt {attempts}) — 同一条件で再生成",
            file=sys.stderr,
        )

        if min_interval_sec > 0:
            pause_fn(min_interval_sec)
