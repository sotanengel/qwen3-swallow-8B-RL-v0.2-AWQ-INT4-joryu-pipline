"""vLLM 推論クライアントの薄いラッパ。

- `vllm` は遅延 import (テスト環境では未インストールのまま import 可能)
- `chat_via_template` がメイン入口: トークナイザの chat_template を使うので
  AWQ-INT4 reasoning モデルでも崩れない。
- per-call の sampling kwargs で row 単位の上書きを受ける。
- `enable_thinking` で推論/非推論モードを切替 (Qwen3 系の chat_template が解釈)。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from joryu.config import ModelConfig, VllmConfig
from joryu.paths import resolve_limits_probe_path
from joryu.tool_calls import (
    ParsedToolCall,
    extract_tool_calls_with_diagnostics,
)
from joryu.vllm_limits import clamp_model_limits, load_probe_limits

__all__ = [
    "ChatResult",
    "SupportsChat",
    "VllmClient",
    "VllmError",
    "VllmHttpClient",
    "build_chat_template_kwargs",
    "compute_effective_max_tokens",
    "extract_known_tool_names",
    "resolve_chat_client",
    "resolve_vllm_serve_url",
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
    tool_calls: tuple[ParsedToolCall, ...] = ()
    # `<think>` / tool_call ブロック除去前の生 completion テキスト。
    # novel format 出現時の事後解析用 (#103)。
    raw_completion: str | None = None
    # parser が拾えなかった tool_call らしき残骸 (snippets)。
    suspected_unparsed_tool_calls: tuple[str, ...] = ()


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
    """Qwen3 chat_template 用 kwargs。

    #94 で mode=auto 削除に伴い `None` を許容しなくなった。
    呼び出し側 (distill は常に True / curate.judge_mode は True|False) で明示する。
    """
    return {"enable_thinking": enable_thinking}


class SupportsChat(Protocol):
    """テスト用 fake と本物クライアントが満たすプロトコル。"""

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult: ...


def extract_known_tool_names(tools: list[dict[str, Any]] | None) -> set[str]:
    """OpenAI function schema 配列から既知ツール名集合を抽出。

    bare JSON 形式 tool_call の保守的検出用 (#103)。
    """
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
        **sampling_overrides: Any,
    ) -> ChatResult:
        """トークナイザの chat_template を使って生成。`ChatResult` を返す。"""
        self._load()
        chat_kwargs: dict[str, Any] = {"use_tqdm": False}
        chat_kwargs["chat_template_kwargs"] = build_chat_template_kwargs(enable_thinking)
        if tools:
            chat_kwargs["tools"] = tools

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
        known = extract_known_tool_names(tools)
        tool_calls, answer, diagnostics = extract_tool_calls_with_diagnostics(
            answer,
            known_tool_names=known or None,
        )
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
            tool_calls=tuple(tool_calls),
            raw_completion=content,
            suspected_unparsed_tool_calls=tuple(
                diagnostics.get("suspected_unparsed_tool_calls", [])
            ),
        )

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


class VllmError(RuntimeError):
    """vLLM 関連エラー。"""


def resolve_vllm_serve_url(vllm_cfg: VllmConfig) -> str | None:
    """常駐 LLM デーモン URL。未設定時 None (in-process ロード)。"""
    env_url = os.environ.get("JORYU_VLLM_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    cfg_url = (vllm_cfg.serve_url or "").strip()
    if cfg_url:
        return cfg_url.rstrip("/")
    return None


def resolve_chat_client(model_cfg: ModelConfig, vllm_cfg: VllmConfig) -> SupportsChat:
    """HTTP デーモン URL があれば VllmHttpClient、未設定なら in-process VllmClient。"""
    url = resolve_vllm_serve_url(vllm_cfg)
    if url:
        return VllmHttpClient(url)
    return VllmClient.from_config(model_cfg, vllm_cfg)


class VllmHttpClient:
    """常駐 joryu-llm-serve へ HTTP で推論を委譲するクライアント (vllm 非 import)。"""

    def __init__(self, base_url: str, *, timeout_s: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        payload = {
            "messages": messages,
            "enable_thinking": enable_thinking,
            "tools": tools,
            "sampling": dict(sampling_overrides),
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v1/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise VllmError(f"vLLM daemon HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise VllmError(f"vLLM daemon unreachable at {self._base_url}: {exc}") from exc

        tool_calls = tuple(
            ParsedToolCall(name=tc["name"], arguments=tc.get("arguments", {}), raw="")
            for tc in data.get("tool_calls", [])
        )
        suspected = data.get("suspected_unparsed_tool_calls") or []
        return ChatResult(
            thinking=data.get("thinking"),
            answer=data.get("answer", ""),
            finish_reason=data.get("finish_reason"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            effective_max_tokens=data.get("effective_max_tokens"),
            tool_calls=tool_calls,
            raw_completion=data.get("raw_completion"),
            suspected_unparsed_tool_calls=tuple(s for s in suspected if isinstance(s, str)),
        )

    def close(self) -> None:
        return None
