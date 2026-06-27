"""JSONL レコード構築 (#251)。"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from joryu.prompt_bank import EffectiveSampling, PromptRow
from joryu.vllm.protocol import ChatResult

logger = logging.getLogger(__name__)


def build_record(
    *,
    row: PromptRow,
    eff: EffectiveSampling,
    thinking: str | None,
    answer: str,
    model_name: str,
    config_hash: str,
    chat: ChatResult,
    turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sampling = dict(eff.sampling)
    if chat.effective_max_tokens is not None:
        sampling["effective_max_tokens"] = chat.effective_max_tokens
    suspected = list(chat.suspected_unparsed_tool_calls)
    if suspected:
        logger.warning(
            "[distill] suspected unparsed tool_call patterns in answer: prompt=%r hints=%s",
            row.prompt[:80],
            suspected,
        )
    return {
        "prompt": row.prompt,
        "category": row.category,
        "style_id": eff.style_id,
        "system_prompt": eff.system_prompt,
        "sampling": sampling,
        "thinking_trace": thinking,
        "reasoning": thinking or "",
        "answer": answer,
        "model": model_name,
        "config_hash": config_hash,
        "finish_reason": chat.finish_reason,
        "prompt_tokens": chat.prompt_tokens,
        "completion_tokens": chat.completion_tokens,
        "tools": eff.tools,
        "tool_ids_requested": row.tool_ids,
        "tool_calls": [asdict(c) for c in chat.tool_calls],
        "turns": turns or [],
        "raw_completion": chat.raw_completion,
        "suspected_unparsed_tool_calls": suspected,
        "created_at": datetime.now(UTC).isoformat(),
    }


def record_from_chat(
    chat: ChatResult,
    *,
    row: PromptRow,
    eff: EffectiveSampling,
    model_name: str,
    config_hash: str,
    turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_record(
        row=row,
        eff=eff,
        thinking=chat.thinking,
        answer=(chat.answer or "").strip(),
        model_name=model_name,
        config_hash=config_hash,
        chat=chat,
        turns=turns,
    )


__all__ = ["build_record", "record_from_chat"]
