"""vLLM クライアント共通ユーティリティ。"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_PROMPT_TOKEN_MARGIN = 32
_MIN_EFFECTIVE_MAX_TOKENS = 64

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
    "compute_effective_max_tokens",
    "extract_known_tool_names",
    "extract_thinking",
    "normalize_vllm_serve_base_url",
]
