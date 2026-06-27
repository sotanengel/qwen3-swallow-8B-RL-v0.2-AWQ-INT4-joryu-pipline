"""vLLM クライアント Protocol と結果型。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from joryu.tool_calls import ParsedToolCall


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
    raw_completion: str | None = None
    suspected_unparsed_tool_calls: tuple[str, ...] = ()


class SupportsChat(Protocol):
    """テスト用 fake と本物クライアントが満たすプロトコル。"""

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult: ...


class SupportsChatStream(Protocol):
    """OpenAI SSE streaming 対応クライアント。"""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> AsyncIterator[Any]: ...


class VllmError(RuntimeError):
    """vLLM 関連エラー。"""


__all__ = [
    "ChatResult",
    "SupportsChat",
    "SupportsChatStream",
    "VllmError",
]
