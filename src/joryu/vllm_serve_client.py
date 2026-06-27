"""OpenAI 互換 vllm serve クライアント — 後方互換 shim (#256)。"""

from joryu.vllm.common import normalize_vllm_serve_base_url
from joryu.vllm.serve import (
    VllmServeClient,
    build_openai_chat_request,
    openai_response_to_chat_result,
)

__all__ = [
    "VllmServeClient",
    "build_openai_chat_request",
    "normalize_vllm_serve_base_url",
    "openai_response_to_chat_result",
]
