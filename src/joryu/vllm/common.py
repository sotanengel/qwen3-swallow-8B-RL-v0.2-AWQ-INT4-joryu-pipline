"""vLLM クライアント共通ユーティリティ。"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from joryu.vllm.protocol import VllmError

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_PROMPT_TOKEN_MARGIN = 32
_MIN_EFFECTIVE_MAX_TOKENS = 64
_VLLM_CHARS_PER_TOKEN_SLOT = 128

DEFAULT_LOCAL_VLLM_URL = "http://localhost:8100"

os.environ.setdefault("VLLM_USE_DEEP_GEMM", "0")
os.environ.setdefault("VLLM_DEEP_GEMM_WARMUP", "skip")
os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")


def extract_thinking(text: str) -> tuple[str | None, str]:
    """`<think>…</think>` を切り出して (思考, 本文) を返す。"""
    m = _THINK_RE.search(text)
    thinking = m.group(1).strip() if m else None
    body = _THINK_RE.sub("", text).strip()
    return thinking, body


def compute_effective_max_tokens(
    *,
    requested_max_tokens: int,
    max_model_len: int,
    prompt_tokens: int,
    margin: int = _PROMPT_TOKEN_MARGIN,
) -> int:
    """コンテキスト上限内に収まる実効 max_tokens を返す。"""
    budget = max_model_len - prompt_tokens - margin
    effective = min(requested_max_tokens, max(0, budget))
    if effective < _MIN_EFFECTIVE_MAX_TOKENS:
        logger.warning(
            "[vllm] effective max_tokens=%s is low (prompt_tokens=%s, max_model_len=%s)",
            effective,
            prompt_tokens,
            max_model_len,
        )
    return effective


def clamp_max_tokens_for_context(
    *,
    requested_max_tokens: int,
    max_model_len: int,
    prompt_tokens: int | None,
    margin: int = _PROMPT_TOKEN_MARGIN,
) -> int:
    """推定 prompt token 数に基づき max_tokens をクランプする。推定不能時はそのまま返す。"""
    if prompt_tokens is None:
        return requested_max_tokens
    if prompt_tokens + margin + _MIN_EFFECTIVE_MAX_TOKENS > max_model_len:
        raise VllmError(
            f"prompt too long for num_ctx={max_model_len}: "
            f"estimated {prompt_tokens} prompt tokens (margin={margin})"
        )
    return compute_effective_max_tokens(
        requested_max_tokens=requested_max_tokens,
        max_model_len=max_model_len,
        prompt_tokens=prompt_tokens,
        margin=margin,
    )


_CONTEXT_OVERFLOW_INPUT_RE = re.compile(
    r"prompt contains at least (\d+) input tokens",
    re.IGNORECASE,
)
_CONTEXT_OVERFLOW_CHARS_RE = re.compile(
    r"prompt contains (\d+) characters",
    re.IGNORECASE,
)
_CONTEXT_OVERFLOW_VALUE_RE = re.compile(
    r'"parameter"\s*:\s*"input_text"\s*,\s*"value"\s*:\s*(\d+)',
    re.IGNORECASE,
)


def parse_context_overflow_characters(error_detail: str) -> int | None:
    """vLLM HTTP 400 の error body から input 文字数を抽出する。"""
    match = _CONTEXT_OVERFLOW_CHARS_RE.search(error_detail)
    if match:
        return int(match.group(1))
    match = _CONTEXT_OVERFLOW_VALUE_RE.search(error_detail)
    if match:
        return int(match.group(1))
    return None


def parse_context_overflow_input_tokens(error_detail: str) -> int | None:
    """vLLM HTTP 400 の error body から input token 数を抽出する。"""
    match = _CONTEXT_OVERFLOW_INPUT_RE.search(error_detail)
    if match:
        return int(match.group(1))
    return None


def is_context_length_error(error_detail: str) -> bool:
    return is_prompt_context_overflow_error(error_detail)


def is_prompt_context_overflow_error(error_detail: str) -> bool:
    lowered = error_detail.lower()
    if "maximum context length" in lowered:
        return True
    if "input_tokens" in lowered:
        return True
    if "prompt contains" in lowered and "characters" in lowered:
        return True
    if parse_context_overflow_input_tokens(error_detail) is not None:
        return True
    if parse_context_overflow_characters(error_detail) is not None:
        return True
    return False


def vllm_input_char_budget(*, max_model_len: int, effective_max_tokens: int) -> int:
    """vLLM の input_text 文字数上限を見積もる (262144 chars / 2048 output slots 準拠)。"""
    input_slots = max(0, max_model_len - effective_max_tokens)
    return input_slots * _VLLM_CHARS_PER_TOKEN_SLOT


def estimate_prompt_characters(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """リクエスト直前の軽量文字数見積もり。"""
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            total += len(json.dumps(tool_calls, ensure_ascii=False))
    if tools:
        total += len(json.dumps(tools, ensure_ascii=False))
    return total


def ensure_prompt_fits_context_budget(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    max_model_len: int,
    effective_max_tokens: int,
) -> None:
    char_count = estimate_prompt_characters(messages, tools)
    char_budget = vllm_input_char_budget(
        max_model_len=max_model_len,
        effective_max_tokens=effective_max_tokens,
    )
    if char_count > char_budget:
        raise VllmError(
            f"prompt too long for num_ctx={max_model_len}: "
            f"estimated {char_count} characters (budget={char_budget})"
        )


def resolve_serve_effective_max_tokens(
    *,
    messages: list[dict[str, str]],
    model_path: str,
    requested_max_tokens: int,
    max_model_len: int | None,
    enable_thinking: bool,
    tools: list[dict[str, Any]] | None,
) -> tuple[int, int | None]:
    """serve/stream 用: 推定とクランプを行い (effective_max, prompt_tokens) を返す。"""
    if max_model_len is None:
        return requested_max_tokens, None
    from joryu.vllm.prompt_tokens import estimate_chat_prompt_tokens

    prompt_tokens = estimate_chat_prompt_tokens(
        messages,
        model_path=model_path,
        enable_thinking=enable_thinking,
        tools=tools,
    )
    effective = clamp_max_tokens_for_context(
        requested_max_tokens=requested_max_tokens,
        max_model_len=max_model_len,
        prompt_tokens=prompt_tokens,
    )
    ensure_prompt_fits_context_budget(
        messages=messages,
        tools=tools,
        max_model_len=max_model_len,
        effective_max_tokens=effective,
    )
    return effective, prompt_tokens


def build_chat_template_kwargs(enable_thinking: bool) -> dict[str, Any]:
    """Qwen3 chat_template 用 kwargs。"""
    return {"enable_thinking": enable_thinking}


def build_offline_chat_kwargs(
    *,
    enable_thinking: bool,
    tools: list[dict[str, Any]] | None,
    tool_choice: dict[str, Any] | str | None,
) -> dict[str, Any]:
    """vLLM offline ``LLM.chat()`` に渡す chat_kwargs を構築する。"""
    chat_kwargs: dict[str, Any] = {"use_tqdm": False}
    chat_kwargs["chat_template_kwargs"] = build_chat_template_kwargs(enable_thinking)
    if tools:
        chat_kwargs["tools"] = tools
    if tool_choice is not None:
        logger.debug(
            "[vllm] tool_choice=%s ignored: LLM.chat() does not accept it offline (#109)",
            tool_choice,
        )
    return chat_kwargs


def extract_known_tool_names(tools: list[dict[str, Any]] | None) -> set[str]:
    """OpenAI function schema 配列から既知ツール名集合を抽出。"""
    if not tools:
        return set()
    names: set[str] = set()
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict):
            name = fn.get("name")
            if isinstance(name, str):
                names.add(name)
    return names


def normalize_vllm_serve_base_url(base_url: str) -> str:
    """``http://host:port`` または ``.../v1`` 付き URL を base に正規化する。"""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        return url[: -len("/v1")]
    return url


__all__ = [
    "DEFAULT_LOCAL_VLLM_URL",
    "build_chat_template_kwargs",
    "build_offline_chat_kwargs",
    "clamp_max_tokens_for_context",
    "compute_effective_max_tokens",
    "ensure_prompt_fits_context_budget",
    "estimate_prompt_characters",
    "extract_known_tool_names",
    "extract_thinking",
    "is_context_length_error",
    "is_prompt_context_overflow_error",
    "normalize_vllm_serve_base_url",
    "parse_context_overflow_characters",
    "parse_context_overflow_input_tokens",
    "resolve_serve_effective_max_tokens",
    "vllm_input_char_budget",
]
