"""tool intent 検出後の named function 強制リトライ (#109 / compass C10, C14)。"""

from __future__ import annotations

from typing import Any

from joryu.tool_intent import (
    chat_has_tool_calls,
    infer_planned_tool_name,
    needs_tool_call_recovery,
)
from joryu.vllm_client import ChatResult, SupportsChat, extract_known_tool_names

DEFAULT_MAX_RECOVERY_ATTEMPTS = 2


def build_named_function_tool_choice(tool_name: str) -> dict[str, Any]:
    """vLLM OpenAI 互換の named function tool_choice を組み立てる。"""
    return {"type": "function", "function": {"name": tool_name}}


def recover_tool_call(
    client: SupportsChat,
    chat: ChatResult,
    *,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None,
    sampling: dict[str, Any],
    max_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    enable_thinking: bool = True,
) -> tuple[ChatResult, dict[str, Any]]:
    """intent あり & tool_calls 空のとき named function で再送し救済を試みる。

    Returns:
        (最終 ChatResult, tool_call_recovery メタデータ)
    """
    metadata: dict[str, Any] = {
        "attempts": 0,
        "method": None,
        "succeeded": False,
        "tool_name": None,
    }
    if not needs_tool_call_recovery(chat, tools=tools):
        return chat, metadata

    known = extract_known_tool_names(tools)
    combined = "\n".join(
        part for part in (chat.thinking, chat.answer) if isinstance(part, str) and part.strip()
    )
    tool_name = infer_planned_tool_name(combined, known)
    if tool_name is None and known:
        tool_name = sorted(known)[0]
    if tool_name is None:
        return chat, metadata

    metadata["tool_name"] = tool_name
    tool_choice = build_named_function_tool_choice(tool_name)
    final_chat = chat

    for _ in range(max_attempts):
        metadata["attempts"] += 1
        metadata["method"] = "named_function"
        retry_chat = client.chat_via_template(
            messages,
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
            **sampling,
        )
        final_chat = retry_chat
        if chat_has_tool_calls(retry_chat):
            metadata["succeeded"] = True
            return retry_chat, metadata

    return final_chat, metadata


__all__ = [
    "DEFAULT_MAX_RECOVERY_ATTEMPTS",
    "build_named_function_tool_choice",
    "recover_tool_call",
]
