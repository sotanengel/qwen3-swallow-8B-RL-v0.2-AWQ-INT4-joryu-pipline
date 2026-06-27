"""OpenAI 互換 vllm serve へ HTTP で推論を委譲するクライアント。"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from joryu.completion_normalize import normalize_chat_result
from joryu.tool_calls import (
    ParsedToolCall,
)
from joryu.vllm_client import ChatResult, VllmError, extract_known_tool_names, extract_thinking

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "joryu"


def normalize_vllm_serve_base_url(base_url: str) -> str:
    """``http://host:port`` または ``.../v1`` 付き URL を base に正規化する。"""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        return url[: -len("/v1")]
    return url


def build_openai_chat_request(
    messages: list[dict[str, Any]],
    *,
    model: str,
    enable_thinking: bool = True,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
    **sampling_overrides: Any,
) -> dict[str, Any]:
    """OpenAI ``/v1/chat/completions`` 用リクエスト body を組み立てる。

    生 HTTP で送るため ``extra_body`` ラッパは使わない。
    vllm serve は ``chat_template_kwargs`` / ``top_k`` / ``repetition_penalty`` を
    リクエストボディの **トップレベル** で直接受け付ける (OpenAI 拡張)。
    """
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
    """OpenAI / vllm serve の reasoning フィールドを thinking 文字列として取り出す。"""
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


class VllmServeClient:
    """本物 vllm serve (OpenAI 互換) へ HTTP で推論を委譲するクライアント。"""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = 600.0,
    ) -> None:
        self._base_url = normalize_vllm_serve_base_url(base_url)
        self._model = model
        self._timeout_s = timeout_s

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
            model=self._model,
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
            **sampling_overrides,
        )
        effective_max = payload.get("max_tokens")
        if not isinstance(effective_max, int):
            effective_max = None

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
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
            raise VllmError(f"vLLM serve unreachable at {self._base_url}: {exc}") from exc

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
    "normalize_vllm_serve_base_url",
    "openai_response_to_chat_result",
]
