"""OpenAI 互換 vllm serve HTTP クライアント (#256)。"""

from __future__ import annotations

import json
import logging
from typing import Any

from joryu.completion_normalize import normalize_chat_result
from joryu.tool_calls import ParsedToolCall
from joryu.vllm.base import HttpVllmBase
from joryu.vllm.common import (
    clamp_max_tokens_for_context,
    extract_known_tool_names,
    extract_thinking,
    is_context_length_error,
    parse_context_overflow_input_tokens,
    resolve_serve_effective_max_tokens,
)
from joryu.vllm.protocol import ChatResult, VllmError

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "joryu"


def build_openai_chat_request(
    messages: list[dict[str, Any]],
    *,
    model: str,
    enable_thinking: bool = True,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
    **sampling_overrides: Any,
) -> dict[str, Any]:
    """OpenAI ``/v1/chat/completions`` 用リクエスト body を組み立てる。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    for key in ("temperature", "top_p", "max_tokens"):
        if key in sampling_overrides:
            payload[key] = sampling_overrides[key]
    for key in ("top_k", "repetition_penalty"):
        if key in sampling_overrides:
            payload[key] = sampling_overrides[key]
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    return payload


def _parse_tool_call_entry(entry: dict[str, Any]) -> ParsedToolCall:
    fn = entry.get("function") if isinstance(entry, dict) else None
    if not isinstance(fn, dict):
        return ParsedToolCall(name="<malformed>", arguments={}, raw=str(entry))
    name = fn.get("name")
    raw_args = fn.get("arguments", "{}")
    if not isinstance(name, str):
        return ParsedToolCall(name="<malformed>", arguments={}, raw=str(raw_args))
    if isinstance(raw_args, dict):
        return ParsedToolCall(name=name, arguments=raw_args, raw=json.dumps(raw_args))
    raw_str = str(raw_args)
    try:
        parsed = json.loads(raw_str)
    except json.JSONDecodeError:
        return ParsedToolCall(name="<malformed>", arguments={}, raw=raw_str)
    if not isinstance(parsed, dict):
        return ParsedToolCall(name="<malformed>", arguments={}, raw=raw_str)
    return ParsedToolCall(name=name, arguments=parsed, raw=raw_str)


def _reconstruct_raw_completion(
    *,
    content: str,
    reasoning_content: str | None,
) -> str:
    if reasoning_content:
        parts = [f"<think>{reasoning_content}</think>"]
        if content:
            parts.append(content)
        return "\n\n".join(parts)
    return content


def _extract_reasoning_from_message(message: dict[str, Any]) -> str | None:
    for key in ("reasoning_content", "reasoning"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def openai_response_to_chat_result(
    data: dict[str, Any],
    *,
    effective_max_tokens: int | None,
    known_tool_names: set[str] | None = None,
) -> ChatResult:
    """OpenAI chat completion JSON を joryu ``ChatResult`` に変換する。"""
    choices = data.get("choices") or []
    if not choices:
        raise VllmError("vllm serve returned no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)

    reasoning_str = _extract_reasoning_from_message(message)

    openai_tool_calls = message.get("tool_calls") or []
    parsed_from_openai: list[ParsedToolCall] = []
    if isinstance(openai_tool_calls, list):
        for entry in openai_tool_calls:
            if isinstance(entry, dict):
                parsed_from_openai.append(_parse_tool_call_entry(entry))

    if reasoning_str is not None:
        thinking: str | None = reasoning_str
        answer = content.strip()
    else:
        thinking, answer = extract_thinking(content)

    raw_completion = _reconstruct_raw_completion(
        content=content if reasoning_str is None else content,
        reasoning_content=reasoning_str,
    )

    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    preliminary = ChatResult(
        thinking=thinking,
        answer=answer,
        finish_reason=choice.get("finish_reason"),
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        effective_max_tokens=effective_max_tokens,
        tool_calls=tuple(parsed_from_openai),
        raw_completion=raw_completion or None,
        suspected_unparsed_tool_calls=(),
    )
    known_list = list(known_tool_names) if known_tool_names else None
    tools_arg = None
    if known_list:
        tools_arg = [{"type": "function", "function": {"name": n}} for n in known_list]
    return normalize_chat_result(preliminary, tools=tools_arg)


class VllmServeClient(HttpVllmBase):
    """本物 vllm serve (OpenAI 互換) へ HTTP で推論を委譲するクライアント。"""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = _DEFAULT_MODEL,
        max_model_len: int | None = None,
        timeout_s: float = 600.0,
    ) -> None:
        super().__init__(base_url, model=model, timeout_s=timeout_s)
        self._max_model_len = max_model_len

    def _post_chat_completions(
        self,
        payload: dict[str, Any],
        *,
        requested_max_tokens: int,
        prompt_tokens: int | None,
    ) -> dict[str, Any]:
        try:
            return self.post_json_with_retry("/v1/chat/completions", payload)
        except VllmError as exc:
            if (
                self._max_model_len is None
                or prompt_tokens is not None
                or not is_context_length_error(str(exc))
            ):
                raise
            input_tokens = parse_context_overflow_input_tokens(str(exc))
            if input_tokens is None:
                raise
            effective = clamp_max_tokens_for_context(
                requested_max_tokens=requested_max_tokens,
                max_model_len=self._max_model_len,
                prompt_tokens=input_tokens,
            )
            payload["max_tokens"] = effective
            logger.info(
                "[vllm-serve] context overflow retry: input_tokens=%s max_tokens=%s",
                input_tokens,
                effective,
            )
            return self.post_json_with_retry("/v1/chat/completions", payload)

    def chat_via_template(
        self,
        messages: list[dict[str, str]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> ChatResult:
        payload = build_openai_chat_request(
            messages,
            model=self.model,
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
            **sampling_overrides,
        )
        requested_max = payload.get("max_tokens")
        if not isinstance(requested_max, int):
            requested_max = int(sampling_overrides.get("max_tokens", 0)) or 2048
        effective_max, prompt_tokens = resolve_serve_effective_max_tokens(
            messages=messages,
            model_path=self.model,
            requested_max_tokens=requested_max,
            max_model_len=self._max_model_len,
            enable_thinking=enable_thinking,
            tools=tools,
        )
        payload["max_tokens"] = effective_max

        data = self._post_chat_completions(
            payload,
            requested_max_tokens=requested_max,
            prompt_tokens=prompt_tokens,
        )
        known = extract_known_tool_names(tools)
        return openai_response_to_chat_result(
            data,
            effective_max_tokens=effective_max,
            known_tool_names=known or None,
        )

    def close(self) -> None:
        return None


__all__ = [
    "VllmServeClient",
    "build_openai_chat_request",
    "openai_response_to_chat_result",
]
