"""vLLM クライアント抽象 (#256)。

in-process / HTTP sync / async streaming を共通 Protocol で統一する。
"""

from joryu.vllm.common import (
    DEFAULT_LOCAL_VLLM_URL,
    build_chat_template_kwargs,
    build_offline_chat_kwargs,
    compute_effective_max_tokens,
    extract_known_tool_names,
    extract_thinking,
)
from joryu.vllm.factory import (
    resolve_chat_client,
    resolve_stream_chat_client,
    resolve_vllm_serve_url,
)
from joryu.vllm.inproc import VllmClient
from joryu.vllm.protocol import ChatResult, SupportsChat, SupportsChatStream, VllmError
from joryu.vllm.serve import VllmServeClient
from joryu.vllm.stream import StreamChunk, VllmServeStreamClient

__all__ = [
    "ChatResult",
    "DEFAULT_LOCAL_VLLM_URL",
    "StreamChunk",
    "SupportsChat",
    "SupportsChatStream",
    "VllmClient",
    "VllmError",
    "VllmServeClient",
    "VllmServeStreamClient",
    "build_chat_template_kwargs",
    "build_offline_chat_kwargs",
    "compute_effective_max_tokens",
    "extract_known_tool_names",
    "extract_thinking",
    "resolve_chat_client",
    "resolve_stream_chat_client",
    "resolve_vllm_serve_url",
]
