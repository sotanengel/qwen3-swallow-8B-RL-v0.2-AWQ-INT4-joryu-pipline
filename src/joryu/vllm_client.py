"""vLLM 推論クライアントの薄いラッパ。

- `vllm` は遅延 import (テスト環境では未インストールのまま import 可能)
- `chat_via_template` がメイン入口: トークナイザの chat_template を使うので
  AWQ-INT4 reasoning モデルでも崩れない。
- per-call の sampling kwargs で row 単位の上書きを受ける。
- `enable_thinking` で推論/非推論モードを切替 (Qwen3 系の chat_template が解釈)。
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from joryu.config import ModelConfig, VllmConfig
from joryu.vllm_limits import clamp_model_limits, load_probe_limits

__all__ = [
    "ChatResult",
    "SupportsChat",
    "VllmClient",
    "VllmError",
    "extract_thinking",
    "compute_effective_max_tokens",
]

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_PROMPT_TOKEN_MARGIN = 32
_MIN_EFFECTIVE_MAX_TOKENS = 64

os.environ.setdefault("VLLM_USE_DEEP_GEMM", "0")
os.environ.setdefault("VLLM_DEEP_GEMM_WARMUP", "skip")
os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")


@dataclass(frozen=True)
class ChatResult:
    """vLLM chat 1 回分の結果。"""

    thinking: str | None
    answer: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    effective_max_tokens: int | None = None


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


class SupportsChat(Protocol):
    """テスト用 fake と本物クライアントが満たすプロトコル。"""

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        **sampling_overrides: Any,
    ) -> ChatResult: ...


class VllmClient:
    """vLLM `LLM.chat` を呼ぶクライアント。"""

    def __init__(
        self,
        model_path: str,
        *,
        max_model_len: int,
        dtype: str,
        gpu_memory_utilization: float,
        enforce_eager: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        repetition_penalty: float,
        max_tokens: int,
        seed: int,
        quantization: str | None,
        limits_probe_file: str | None = None,
    ) -> None:
        self._model_path = model_path
        self._max_model_len = max_model_len
        self._dtype = dtype
        self._gpu_memory_utilization = gpu_memory_utilization
        self._enforce_eager = enforce_eager
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._max_tokens = max_tokens
        self._seed = seed
        self._quantization = quantization
        self._limits_probe_file = limits_probe_file
        self._llm: Any = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        with self._lock:
            if self._llm is not None:
                return
            try:
                from vllm import LLM
            except ImportError as exc:
                raise ImportError(
                    "vllm is required for inference; install with `uv sync --extra vllm`"
                ) from exc

            llm_kwargs: dict[str, Any] = {
                "model": self._model_path,
                "max_model_len": self._max_model_len,
                "dtype": self._dtype,
                "enforce_eager": self._enforce_eager,
                "gpu_memory_utilization": self._gpu_memory_utilization,
                "seed": self._seed,
            }
            if self._quantization:
                llm_kwargs["quantization"] = self._quantization
            try:
                self._llm = LLM(**llm_kwargs)
            except Exception as exc:
                raise VllmError(f"failed to load vLLM model: {exc}") from exc

    def _estimate_prompt_tokens(
        self,
        messages: list[dict[str, str]],
        *,
        chat_template_kwargs: dict[str, Any],
    ) -> int | None:
        try:
            tokenizer = self._llm.get_tokenizer()
            token_ids = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                chat_template_kwargs=chat_template_kwargs,
            )
            if isinstance(token_ids, list):
                return len(token_ids)
            if hasattr(token_ids, "input_ids"):
                return len(token_ids.input_ids)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[vllm] prompt token estimate failed: %s", exc)
        return None

    def _sampling_params(self, **overrides: Any) -> Any:
        from vllm import SamplingParams

        return SamplingParams(
            max_tokens=overrides.get("max_tokens", self._max_tokens),
            temperature=overrides.get("temperature", self._temperature),
            top_p=overrides.get("top_p", self._top_p),
            top_k=overrides.get("top_k", self._top_k),
            repetition_penalty=overrides.get("repetition_penalty", self._repetition_penalty),
        )

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        **sampling_overrides: Any,
    ) -> ChatResult:
        """トークナイザの chat_template を使って生成。`ChatResult` を返す。"""
        self._load()
        chat_kwargs: dict[str, Any] = {"use_tqdm": False}
        chat_kwargs["chat_template_kwargs"] = {"enable_thinking": enable_thinking}

        requested_max = int(sampling_overrides.get("max_tokens", self._max_tokens))
        prompt_tokens = self._estimate_prompt_tokens(
            messages,
            chat_template_kwargs=chat_kwargs["chat_template_kwargs"],
        )
        effective_max = requested_max
        if prompt_tokens is not None:
            effective_max = compute_effective_max_tokens(
                requested_max_tokens=requested_max,
                max_model_len=self._max_model_len,
                prompt_tokens=prompt_tokens,
            )
        params = self._sampling_params(**{**sampling_overrides, "max_tokens": effective_max})
        outputs = self._llm.chat(messages, params, **chat_kwargs)
        request_output = outputs[0]
        completion = request_output.outputs[0]
        content: str = completion.text or ""
        thinking, answer = extract_thinking(content)
        out_prompt_tokens = (
            len(request_output.prompt_token_ids)
            if getattr(request_output, "prompt_token_ids", None) is not None
            else prompt_tokens
        )
        token_ids = getattr(completion, "token_ids", None)
        out_completion_tokens = len(token_ids) if token_ids is not None else None
        return ChatResult(
            thinking=thinking,
            answer=answer,
            finish_reason=getattr(completion, "finish_reason", None),
            prompt_tokens=out_prompt_tokens,
            completion_tokens=out_completion_tokens,
            effective_max_tokens=effective_max,
        )

    @classmethod
    def from_config(cls, model_cfg: ModelConfig, vllm_cfg: VllmConfig) -> VllmClient:
        probe_path = model_cfg.limits_probe_file
        if probe_path and not Path(probe_path).is_absolute():
            probe_path = str(Path(probe_path))
        probe = load_probe_limits(probe_path)
        num_ctx, num_predict = clamp_model_limits(
            requested_ctx=model_cfg.num_ctx,
            requested_predict=model_cfg.num_predict,
            probe=probe,
        )
        return cls(
            model_path=vllm_cfg.model_path,
            max_model_len=num_ctx,
            dtype=vllm_cfg.dtype,
            gpu_memory_utilization=vllm_cfg.gpu_memory_utilization,
            enforce_eager=vllm_cfg.enforce_eager,
            temperature=model_cfg.temperature,
            top_p=model_cfg.top_p,
            top_k=model_cfg.top_k,
            repetition_penalty=model_cfg.repetition_penalty,
            max_tokens=num_predict,
            seed=model_cfg.seed,
            quantization=vllm_cfg.quantization,
            limits_probe_file=probe_path,
        )

    def close(self) -> None:
        with self._lock:
            self._llm = None


class VllmError(RuntimeError):
    """vLLM 関連エラー。"""
