"""OpenAI 互換 vllm serve async SSE streaming クライアント (#256)。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from joryu.completion_normalize import normalize_chat_result
from joryu.http_client import build_httpx_timeout, get_shared_async_client
from joryu.tool_calls import ParsedToolCall
from joryu.vllm.common import extract_known_tool_names
from joryu.vllm.protocol import ChatResult, VllmError
from joryu.vllm.serve import (
    _DEFAULT_MODEL,
    _reconstruct_raw_completion,
    build_openai_chat_request,
)

logger = logging.getLogger(__name__)

StreamKind = Literal["thinking", "content", "tool_call_partial", "done"]


@dataclass(frozen=True)
class StreamChunk:
    """1 SSE delta 相当のストリーム断片。"""

    kind: StreamKind
    delta: str = ""
    finish_reason: str | None = None
    tool_call_index: int | None = None
    tool_call_id: str | None = None
    tool_call_name: str | None = None
    tool_call_arguments_delta: str | None = None
    result: ChatResult | None = None


@dataclass
class _ToolCallPartial:
    call_id: str = ""
    name: str = ""
    arguments: str = ""


class ToolCallStreamAccumulator:
    """OpenAI streaming tool_calls delta を蓄積する。"""

    def __init__(self) -> None:
        self._calls: dict[int, _ToolCallPartial] = {}

    def feed(
        self,
        *,
        tool_call_index: int,
        call_id: str | None = None,
        name: str | None = None,
        arguments_delta: str | None = None,
    ) -> None:
        partial = self._calls.setdefault(tool_call_index, _ToolCallPartial())
        if call_id:
            partial.call_id = call_id
        if name:
            partial.name = name
        if arguments_delta:
            partial.arguments += arguments_delta

    def finalize(self) -> tuple[ParsedToolCall, ...]:
        calls: list[ParsedToolCall] = []
        for index in sorted(self._calls):
            partial = self._calls[index]
            raw_args = partial.arguments or "{}"
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning("[stream] malformed tool arguments at index %s", index)
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            calls.append(
                ParsedToolCall(name=partial.name or "<unknown>", arguments=parsed, raw=raw_args)
            )
        return tuple(calls)


def openai_sse_data_to_chunks(data: str) -> list[StreamChunk]:
    if data.strip() == "[DONE]":
        return [StreamChunk(kind="done")]

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("[stream] invalid SSE JSON: %s", data[:120])
        return []

    choices = payload.get("choices") or []
    if not choices:
        return []

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    delta = choice.get("delta") or {}
    chunks: list[StreamChunk] = []

    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
    if isinstance(reasoning, str) and reasoning:
        chunks.append(StreamChunk(kind="thinking", delta=reasoning))

    content = delta.get("content")
    if isinstance(content, str) and content:
        chunks.append(StreamChunk(kind="content", delta=content))

    tool_calls = delta.get("tool_calls") or []
    if isinstance(tool_calls, list):
        for entry in tool_calls:
            if not isinstance(entry, dict):
                continue
            fn = entry.get("function") if isinstance(entry.get("function"), dict) else {}
            chunks.append(
                StreamChunk(
                    kind="tool_call_partial",
                    tool_call_index=entry.get("index"),
                    tool_call_id=entry.get("id"),
                    tool_call_name=fn.get("name"),
                    tool_call_arguments_delta=fn.get("arguments"),
                )
            )

    if finish_reason and not chunks:
        chunks.append(StreamChunk(kind="done", finish_reason=str(finish_reason)))

    return chunks


def parse_openai_sse_data(data: str) -> list[StreamChunk]:
    """OpenAI SSE ``data:`` 行 1 件を ``StreamChunk`` 列に変換する。"""
    return openai_sse_data_to_chunks(data)


def _assemble_chat_result(
    *,
    content: str,
    thinking: str | None,
    finish_reason: str | None,
    tool_calls: tuple[ParsedToolCall, ...],
    known_tool_names: set[str] | None,
    effective_max_tokens: int | None,
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    raw_completion = _reconstruct_raw_completion(
        content=content if thinking is None else content,
        reasoning_content=thinking,
    )
    preliminary = ChatResult(
        thinking=thinking,
        answer=content.strip(),
        finish_reason=finish_reason,
        prompt_tokens=None,
        completion_tokens=None,
        effective_max_tokens=effective_max_tokens,
        tool_calls=tool_calls,
        raw_completion=raw_completion or None,
        suspected_unparsed_tool_calls=(),
    )
    if tools is None and known_tool_names:
        tools = [
            {"type": "function", "function": {"name": name}} for name in sorted(known_tool_names)
        ]
    return normalize_chat_result(preliminary, tools=tools)


class VllmServeStreamClient:
    """vllm serve OpenAI API へ ``stream=true`` で接続するクライアント。"""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        from joryu.vllm.common import normalize_vllm_serve_base_url

        self._base_url = normalize_vllm_serve_base_url(base_url)
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport
        self._http_client = http_client

    async def _iter_stream_chunks(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> AsyncIterator[StreamChunk]:
        payload = build_openai_chat_request(
            messages,
            model=self._model,
            enable_thinking=enable_thinking,
            tools=tools,
            tool_choice=tool_choice,
            **sampling_overrides,
        )
        payload["stream"] = True
        effective_max = payload.get("max_tokens")
        if not isinstance(effective_max, int):
            effective_max = None

        known = extract_known_tool_names(tools)
        url = f"{self._base_url}/v1/chat/completions"
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        finish_reason: str | None = None
        tool_acc = ToolCallStreamAccumulator()

        owns_client = False
        if self._http_client is not None:
            http = self._http_client
        elif self._transport is not None:
            http = httpx.AsyncClient(
                transport=self._transport,
                timeout=build_httpx_timeout(read_s=self._timeout_s),
            )
            owns_client = True
        else:
            http = get_shared_async_client(read_timeout_s=self._timeout_s)

        try:
            async with http.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    for chunk in openai_sse_data_to_chunks(data):
                        if chunk.kind == "thinking":
                            thinking_parts.append(chunk.delta)
                            yield chunk
                        elif chunk.kind == "content":
                            content_parts.append(chunk.delta)
                            yield chunk
                        elif chunk.kind == "tool_call_partial":
                            if chunk.tool_call_index is not None:
                                tool_acc.feed(
                                    tool_call_index=chunk.tool_call_index,
                                    call_id=chunk.tool_call_id,
                                    name=chunk.tool_call_name,
                                    arguments_delta=chunk.tool_call_arguments_delta,
                                )
                        elif chunk.kind == "done":
                            if chunk.finish_reason:
                                finish_reason = chunk.finish_reason
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise VllmError(f"vLLM serve HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            raise VllmError(f"vLLM serve unreachable at {self._base_url}: {exc}") from exc
        finally:
            if owns_client:
                await http.aclose()

        thinking = "".join(thinking_parts).strip() or None
        content = "".join(content_parts)
        tool_calls = tool_acc.finalize()
        if tool_calls and finish_reason is None:
            finish_reason = "tool_calls"
        if finish_reason is None:
            finish_reason = "stop"

        result = _assemble_chat_result(
            content=content,
            thinking=thinking,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            known_tool_names=known or None,
            effective_max_tokens=effective_max,
            tools=tools,
        )
        yield StreamChunk(kind="done", finish_reason=finish_reason, result=result)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        **sampling_overrides: Any,
    ) -> AsyncIterator[StreamChunk]:
        try:
            async with asyncio.timeout(self._timeout_s):
                async for chunk in self._iter_stream_chunks(
                    messages,
                    enable_thinking=enable_thinking,
                    tools=tools,
                    tool_choice=tool_choice,
                    **sampling_overrides,
                ):
                    yield chunk
        except TimeoutError as exc:
            raise VllmError(
                f"vLLM stream timed out after {self._timeout_s}s at {self._base_url}",
            ) from exc


__all__ = [
    "StreamChunk",
    "ToolCallStreamAccumulator",
    "VllmServeStreamClient",
    "openai_sse_data_to_chunks",
    "parse_openai_sse_data",
]
