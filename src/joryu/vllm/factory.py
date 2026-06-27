"""vLLM クライアント factory (#256)。"""

from __future__ import annotations

import os

from joryu.config import ModelConfig, VllmConfig
from joryu.vllm.common import DEFAULT_LOCAL_VLLM_URL
from joryu.vllm.inproc import VllmClient
from joryu.vllm.protocol import SupportsChat, SupportsChatStream, VllmError
from joryu.vllm.serve import VllmServeClient
from joryu.vllm.stream import VllmServeStreamClient


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
        return VllmServeClient(url or DEFAULT_LOCAL_VLLM_URL, model=vllm_cfg.model_path)
    raise VllmError(f"unknown vllm.backend: {backend!r}")


def resolve_stream_chat_client(
    model_cfg: ModelConfig,
    vllm_cfg: VllmConfig,
) -> SupportsChatStream | None:
    """backend が vllm-serve のときのみ streaming クライアントを返す。"""
    del model_cfg
    if vllm_cfg.backend != "vllm-serve":
        return None
    url = resolve_vllm_serve_url(vllm_cfg)
    return VllmServeStreamClient(url or DEFAULT_LOCAL_VLLM_URL, model=vllm_cfg.model_path)


__all__ = [
    "resolve_chat_client",
    "resolve_stream_chat_client",
    "resolve_vllm_serve_url",
]
