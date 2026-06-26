"""蒸留生成の打ち切り検出と同一条件再試行。"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

from joryu.truncation import record_looks_truncated
from joryu.vllm_client import ChatResult, SupportsChat

TRUNCATION_RETRY_ALERT_THRESHOLD = 3


def _bump_max_tokens_for_length_retry(
    sampling: dict[str, Any],
    cap: int,
) -> dict[str, Any]:
    """finish_reason=length の再試行向けに max_tokens を 1.5x 拡大 (cap でクランプ)。"""
    updated = dict(sampling)
    current = updated.get("max_tokens")
    if not isinstance(current, int) or current <= 0:
        return updated
    bumped = min(max(int(current * 1.5), current + 1), cap)
    updated["max_tokens"] = bumped
    return updated


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
    max_tokens_cap: int | None = None,
    max_attempts: int | None = None,
    on_retry: Callable[[int, dict[str, Any]], None] | None = None,
    log: Callable[..., Any] | None = None,
    time_fn: Callable[[], float] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> tuple[dict[str, Any] | None, int]:
    """打ち切りでないレコードが得られるまで再生成する。

    Qwen3 thinking モード固定で動作する (#94 で nothinking/auto 削除済み)。
    finish_reason=length のときは max_tokens を 1.5x 拡大 (max_tokens_cap まで)。
    max_attempts 到達時は最後の打ち切りレコードを truncation_retry_capped 付きで返す。
    deadline 到達時にまだ打ち切りの場合は (None, attempts) を返す。
    """
    now_fn = time_fn or time.time
    pause_fn = sleep_fn or time.sleep
    emit = log if log is not None else lambda *_a, **_k: None
    attempts = 0
    active_sampling = dict(sampling)

    while True:
        if deadline is not None and now_fn() >= deadline:
            return None, attempts

        attempts += 1
        if chat_fn is None:
            chat = client.chat_via_template(
                messages,
                enable_thinking=True,
                tools=tools,
                **active_sampling,
            )
        else:
            chat = chat_fn(
                messages,
                tools=tools,
                **active_sampling,
            )
        record = build_record(chat)
        if not record_looks_truncated(record):
            record["generation_attempts"] = attempts
            return record, attempts

        if max_attempts is not None and attempts >= max_attempts:
            record["generation_attempts"] = attempts
            record["truncation_retry_capped"] = True
            return record, attempts

        if on_retry is not None and attempts >= TRUNCATION_RETRY_ALERT_THRESHOLD:
            on_retry(attempts, record)

        finish_reason = record.get("finish_reason")
        if finish_reason == "length" and max_tokens_cap is not None:
            prev = active_sampling.get("max_tokens")
            active_sampling = _bump_max_tokens_for_length_retry(active_sampling, max_tokens_cap)
            new = active_sampling.get("max_tokens")
            emit(
                f"[joryu-distill] 打ち切り検出 (attempt {attempts}) — "
                f"max_tokens {prev} → {new} で再生成",
                file=sys.stderr,
            )
        else:
            emit(
                f"[joryu-distill] 打ち切り検出 (attempt {attempts}) — 同一条件で再生成",
                file=sys.stderr,
            )

        if min_interval_sec > 0:
            pause_fn(min_interval_sec)
