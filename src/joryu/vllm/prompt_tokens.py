"""chat プロンプトの token 数推定（vLLM LLM ロード不要）。"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_tokenizer_cache: dict[str, Any] = {}
_tokenizer_lock = threading.Lock()


def estimate_chat_prompt_tokens(
    messages: list[dict[str, str]],
    *,
    model_path: str,
    enable_thinking: bool,
    tools: list[dict[str, Any]] | None = None,
) -> int | None:
    """transformers tokenizer で chat_template 適用後の token 数を推定する。"""
    try:
        from transformers import AutoTokenizer
    except ImportError:
        logger.debug("[vllm] transformers unavailable for prompt token estimate")
        return None

    with _tokenizer_lock:
        tokenizer = _tokenizer_cache.get(model_path)
        if tokenizer is None:
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[vllm] tokenizer load failed for %s: %s", model_path, exc)
                return None
            _tokenizer_cache[model_path] = tokenizer

    template_kwargs: dict[str, Any] = {
        "messages": messages,
        "add_generation_prompt": True,
        "tokenize": True,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    if tools:
        template_kwargs["tools"] = tools
    try:
        token_ids = tokenizer.apply_chat_template(**template_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[vllm] prompt token estimate failed: %s", exc)
        return None

    if isinstance(token_ids, list):
        return len(token_ids)
    if hasattr(token_ids, "input_ids"):
        return len(token_ids.input_ids)
    return None


__all__ = ["estimate_chat_prompt_tokens"]
