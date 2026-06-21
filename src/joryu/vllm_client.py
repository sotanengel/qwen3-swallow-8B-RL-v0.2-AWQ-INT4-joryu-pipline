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
from typing import Any, Protocol

from joryu.config import ModelConfig, VllmConfig

__all__ = [
    "SupportsChat",
    "VllmClient",
    "VllmError",
    "extract_thinking",
]

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

os.environ.setdefault("VLLM_USE_DEEP_GEMM", "0")
os.environ.setdefault("VLLM_DEEP_GEMM_WARMUP", "skip")
os.environ.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")


def extract_thinking(text: str) -> tuple[str | None, str]:
    """`<think>…</think>` を切り出して (思考, 本文) を返す。"""
    m = _THINK_RE.search(text)
    thinking = m.group(1).strip() if m else None
    body = _THINK_RE.sub("", text).strip()
    return thinking, body


class SupportsChat(Protocol):
    """テスト用 fake と本物クライアントが満たすプロトコル。"""

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        **sampling_overrides: Any,
    ) -> tuple[str | None, str]: ...


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
    ) -> tuple[str | None, str]:
        """トークナイザの chat_template を使って生成。`(thinking, answer)` を返す。"""
        self._load()
        params = self._sampling_params(**sampling_overrides)
        chat_kwargs: dict[str, Any] = {"use_tqdm": False}
        # Qwen3 chat_template は enable_thinking フラグを受け付ける。
        chat_kwargs["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
        outputs = self._llm.chat(messages, params, **chat_kwargs)
        content: str = outputs[0].outputs[0].text or ""
        return extract_thinking(content)

    @classmethod
    def from_config(cls, model_cfg: ModelConfig, vllm_cfg: VllmConfig) -> VllmClient:
        return cls(
            model_path=vllm_cfg.model_path,
            max_model_len=model_cfg.num_ctx,
            dtype=vllm_cfg.dtype,
            gpu_memory_utilization=vllm_cfg.gpu_memory_utilization,
            enforce_eager=vllm_cfg.enforce_eager,
            temperature=model_cfg.temperature,
            top_p=model_cfg.top_p,
            top_k=model_cfg.top_k,
            repetition_penalty=model_cfg.repetition_penalty,
            max_tokens=model_cfg.num_predict,
            seed=model_cfg.seed,
            quantization=vllm_cfg.quantization,
        )

    def close(self) -> None:
        with self._lock:
            self._llm = None


class VllmError(RuntimeError):
    """vLLM 関連エラー。"""
