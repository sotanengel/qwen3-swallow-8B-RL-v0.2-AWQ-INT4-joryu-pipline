"""チャットターン完了時の JSONL レコード構築。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from joryu.vllm_client import ChatResult

CHAT_CATEGORY = "人間との対話"


def build_chat_record(
    *,
    prompt: str,
    style_id: str,
    system_prompt: str,
    session_id: str,
    turn_index: int,
    thinking: str | None,
    answer: str,
    model_name: str,
    config_hash: str,
    chat: ChatResult,
    turns: list[dict[str, Any]],
    sampling: dict[str, Any],
    tools: list[dict[str, Any]],
    tool_ids: list[str],
) -> dict[str, Any]:
    """distill._build_record と互換のスキーマ + session_id / turn_index。"""
    eff_sampling = dict(sampling)
    if chat.effective_max_tokens is not None:
        eff_sampling["effective_max_tokens"] = chat.effective_max_tokens
    suspected = list(chat.suspected_unparsed_tool_calls)
    return {
        "prompt": prompt,
        "category": CHAT_CATEGORY,
        "style_id": style_id,
        "system_prompt": system_prompt,
        "sampling": eff_sampling,
        "thinking_trace": thinking,
        "reasoning": thinking or "",
        "answer": answer,
        "model": model_name,
        "config_hash": config_hash,
        "finish_reason": chat.finish_reason,
        "prompt_tokens": chat.prompt_tokens,
        "completion_tokens": chat.completion_tokens,
        "tools": tools,
        "tool_ids_requested": tool_ids,
        "tool_calls": [asdict(c) for c in chat.tool_calls],
        "turns": turns,
        "raw_completion": chat.raw_completion,
        "suspected_unparsed_tool_calls": suspected,
        "created_at": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "turn_index": turn_index,
    }
