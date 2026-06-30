"""vLLM クライアント factory (#256)。"""

from __future__ import annotations

import os

from joryu.config import ModelConfig, VllmConfig
from joryu.paths import resolve_limits_probe_path
from joryu.vllm.common import DEFAULT_LOCAL_VLLM_URL
from joryu.vllm.inproc import VllmClient
from joryu.vllm.protocol import SupportsChat, SupportsChatStream, VllmError
from joryu.vllm.serve import VllmServeClient
from joryu.vllm.stream import VllmServeStreamClient
from joryu.vllm_limits import clamp_model_limits, load_probe_limits


def resolve_max_model_len(model_cfg: ModelConfig) -> int:
    """VRAM probe を反映した effective num_ctx を返す。"""
    probe_path = resolve_limits_probe_path(model_cfg.limits_probe_file)
    probe = load_probe_limits(probe_path)
    num_ctx, _ = clamp_model_limits(
        requested_ctx=model_cfg.num_ctx,
        requested_predict=model_cfg.num_predict,
        probe=probe,
    )
    return num_ctx


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
    """backend 設定に応じて HTTP / in-process クライアントを返す。"""
    backend = vllm_cfg.backend
    if backend == "inproc":
        return VllmClient.from_config(model_cfg, vllm_cfg)

    url = resolve_vllm_serve_url(vllm_cfg)
    if backend == "vllm-serve":
        return VllmServeClient(
            url or DEFAULT_LOCAL_VLLM_URL,
            model=vllm_cfg.model_path,
            max_model_len=resolve_max_model_len(model_cfg),
        )
    raise VllmError(f"unknown vllm.backend: {backend!r}")


def resolve_stream_chat_client(
    model_cfg: ModelConfig,
    vllm_cfg: VllmConfig,
) -> SupportsChatStream | None:
    """backend が vllm-serve のときのみ streaming クライアントを返す。"""
    if vllm_cfg.backend != "vllm-serve":
        return None
    url = resolve_vllm_serve_url(vllm_cfg)
    return VllmServeStreamClient(
        url or DEFAULT_LOCAL_VLLM_URL,
        model=vllm_cfg.model_path,
        max_model_len=resolve_max_model_len(model_cfg),
    )


__all__ = [
    "resolve_chat_client",
    "resolve_max_model_len",
    "resolve_stream_chat_client",
    "resolve_vllm_serve_url",
]
