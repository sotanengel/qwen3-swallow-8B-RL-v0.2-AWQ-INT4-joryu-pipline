"""in-process vLLM クライアント (#256)。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from joryu.completion_normalize import normalize_chat_result
from joryu.config import ModelConfig, VllmConfig
from joryu.paths import resolve_limits_probe_path
from joryu.vllm.common import (
    build_offline_chat_kwargs,
    compute_effective_max_tokens,
    extract_thinking,
)
from joryu.vllm.protocol import ChatResult, VllmError
from joryu.vllm_limits import clamp_model_limits, load_probe_limits

logger = logging.getLogger(__name__)


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
        kv_cache_dtype: str = "auto",
        enable_prefix_caching: bool = False,
        max_num_seqs: int | None = None,
        swap_space_gib: int = 0,
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
        self._kv_cache_dtype = kv_cache_dtype
        self._enable_prefix_caching = enable_prefix_caching
        self._max_num_seqs = max_num_seqs
        self._swap_space_gib = swap_space_gib
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
            if self._kv_cache_dtype and self._kv_cache_dtype != "auto":
                llm_kwargs["kv_cache_dtype"] = self._kv_cache_dtype
            if self._enable_prefix_caching:
                llm_kwargs["enable_prefix_caching"] = True
            if self._max_num_seqs is not None and self._max_num_seqs > 0:
                llm_kwargs["max_num_seqs"] = self._max_num_seqs
            if self._swap_space_gib and self._swap_space_gib > 0:
                llm_kwargs["swap_space"] = self._swap_space_gib
            try:
                self._llm = LLM(**llm_kwargs)
            except Exception as exc:
                raise VllmError(f"failed to load vLLM model: {exc}") from exc

    def _estimate_prompt_tokens(
        self,
        messages: list[dict[str, str]],
        *,
        chat_template_kwargs: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        try:
            tokenizer = self._llm.get_tokenizer()
            template_kwargs: dict[str, Any] = {
                "messages": messages,
                "add_generation_prompt": True,
                "tokenize": True,
                "chat_template_kwargs": chat_template_kwargs,
            }
            if tools:
                template_kwargs["tools"] = tools
            token_ids = tokenizer.apply_chat_template(**template_kwargs)
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
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        """トークナイザの chat_template を使って生成。`ChatResult` を返す。"""
        self._load()
        chat_kwargs = build_offline_chat_kwargs(
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
        )

        requested_max = int(sampling_overrides.get("max_tokens", self._max_tokens))
        prompt_tokens = self._estimate_prompt_tokens(
            messages,
            chat_template_kwargs=chat_kwargs["chat_template_kwargs"],
            tools=tools,
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
        preliminary = ChatResult(
            thinking=thinking,
            answer=answer,
            finish_reason=getattr(completion, "finish_reason", None),
            prompt_tokens=out_prompt_tokens,
            completion_tokens=out_completion_tokens,
            effective_max_tokens=effective_max,
            tool_calls=(),
            raw_completion=content,
            suspected_unparsed_tool_calls=(),
        )
        return normalize_chat_result(preliminary, tools=tools)

    @classmethod
    def from_config(cls, model_cfg: ModelConfig, vllm_cfg: VllmConfig) -> VllmClient:
        probe_path = resolve_limits_probe_path(model_cfg.limits_probe_file)
        probe = load_probe_limits(probe_path)
        num_ctx, num_predict = clamp_model_limits(
            requested_ctx=model_cfg.num_ctx,
            requested_predict=model_cfg.num_predict,
            probe=probe,
        )
        if probe is None and model_cfg.limits_probe_file:
            logger.warning(
                "[vllm] limits probe file missing: %s; using num_ctx=%s num_predict=%s",
                probe_path,
                num_ctx,
                num_predict,
            )
        elif probe is not None and (
            num_ctx < model_cfg.num_ctx or num_predict < model_cfg.num_predict
        ):
            logger.info(
                "[vllm] effective limits from probe: num_ctx=%s num_predict=%s",
                num_ctx,
                num_predict,
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
            kv_cache_dtype=vllm_cfg.kv_cache_dtype,
            enable_prefix_caching=vllm_cfg.enable_prefix_caching,
            max_num_seqs=vllm_cfg.max_num_seqs,
            swap_space_gib=vllm_cfg.swap_space_gib,
            limits_probe_file=str(probe_path),
        )

    def close(self) -> None:
        with self._lock:
            self._llm = None


__all__ = ["VllmClient"]
