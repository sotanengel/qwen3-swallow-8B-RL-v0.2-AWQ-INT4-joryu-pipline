"""Tool loop 実行。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from joryu.chat.token_stream import TokenStreamer
from joryu.tool_call_recovery import recover_tool_call
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import ChatResult, SupportsChat, SupportsChatStream

DEFAULT_MAX_TURNS = 4


def _generate_tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"


def _tool_calls_to_openai(
    tool_calls: tuple[ParsedToolCall, ...],
    *,
    ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if ids is None:
        ids = [_generate_tool_call_id() for _ in tool_calls]
    return [
        {
            "id": call_id,
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments, ensure_ascii=False),
            },
        }
        for call_id, call in zip(ids, tool_calls, strict=True)
    ]


def _append_tool_turn_messages(
    working_messages: list[dict[str, Any]],
    *,
    assistant_content: str,
    tool_calls: tuple[ParsedToolCall, ...],
    tool_results: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    ids = [_generate_tool_call_id() for _ in tool_calls]
    updated: list[dict[str, Any]] = [
        *working_messages,
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": _tool_calls_to_openai(tool_calls, ids=ids),
        },
    ]
    for call_id, (name, content) in zip(ids, tool_results, strict=True):
        updated.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": content,
            }
        )
    return updated


def _tool_call_dedupe_key(call: ParsedToolCall) -> tuple[str, str]:
    return (
        call.name,
        json.dumps(call.arguments, sort_keys=True, ensure_ascii=False),
    )


class ToolLoopRunner:
    """tool loop 制御と ChatResult の積み上げ。"""

    def __init__(
        self,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        tool_loop_dedupe: bool = True,
        token_streamer: TokenStreamer | None = None,
    ) -> None:
        self._max_turns = max_turns
        self._tool_loop_dedupe = tool_loop_dedupe
        self._token_streamer = token_streamer or TokenStreamer()

    async def _chat_sync(
        self,
        client: SupportsChat,
        working_messages: list[dict[str, Any]],
        *,
        tools_arg: list[dict[str, Any]] | None,
        sampling: dict[str, Any],
    ) -> ChatResult:
        return await asyncio.to_thread(
            client.chat_via_template,
            working_messages,
            enable_thinking=True,
            tools=tools_arg,
            **sampling,
        )

    async def _chat_streaming(
        self,
        stream_client: SupportsChatStream,
        column_id: str,
        working_messages: list[dict[str, Any]],
        *,
        tools_arg: list[dict[str, Any]] | None,
        sampling: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any] | ChatResult]:
        chat: ChatResult | None = None
        async for chunk in stream_client.chat_stream(
            working_messages,
            enable_thinking=True,
            tools=tools_arg,
            **sampling,
        ):
            kind = getattr(chunk, "kind", None)
            if kind == "content" and chunk.delta:
                yield {
                    "type": "token",
                    "column": column_id,
                    "delta": chunk.delta,
                }
            elif kind == "done" and chunk.result is not None:
                chat = chunk.result
        if chat is None:
            raise RuntimeError("streaming chat returned no result")
        yield chat

    async def run(
        self,
        *,
        column_id: str,
        working_messages: list[dict[str, Any]],
        column_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        executor: ToolExecutor | None,
        client: SupportsChat,
        stream_client: SupportsChatStream | None = None,
        sampling: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        final_chat: ChatResult | None = None
        exhausted = False
        executed_cache: dict[tuple[str, str], str] = {}
        tools_arg = tools or None

        for turn_index in range(self._max_turns):
            yield {
                "type": "turn_start",
                "column": column_id,
                "turn": turn_index + 1,
            }

            if stream_client is not None:
                chat: ChatResult | None = None
                async for item in self._chat_streaming(
                    stream_client,
                    column_id,
                    working_messages,
                    tools_arg=tools_arg,
                    sampling=sampling,
                ):
                    if isinstance(item, ChatResult):
                        chat = item
                    else:
                        yield item
                if chat is None:
                    yield {"type": "error", "column": column_id, "message": "no chat result"}
                    return
            else:
                chat = await self._chat_sync(
                    client,
                    working_messages,
                    tools_arg=tools_arg,
                    sampling=sampling,
                )
                async for tok in self._token_streamer.stream(column_id, chat.answer or ""):
                    yield tok

            if tools_arg:
                chat, _recovery = await asyncio.to_thread(
                    recover_tool_call,
                    client,
                    chat,
                    messages=working_messages,
                    tools=tools_arg,
                    sampling=sampling,
                )
            final_chat = chat

            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": chat.answer,
                "tool_calls": [asdict(c) for c in chat.tool_calls],
            }
            if chat.raw_completion is not None:
                assistant_turn["raw_completion"] = chat.raw_completion
            turns.append(assistant_turn)

            if not chat.tool_calls or executor is None:
                column_messages.append({"role": "assistant", "content": chat.answer or ""})
                break

            assistant_content = chat.answer or ""
            tool_results: list[tuple[str, str]] = []
            call_ids = [_generate_tool_call_id() for _ in chat.tool_calls]
            for call_id, call in zip(call_ids, chat.tool_calls, strict=True):
                key = _tool_call_dedupe_key(call)
                if self._tool_loop_dedupe and key in executed_cache:
                    result = executed_cache[key]
                else:
                    try:
                        result = await asyncio.to_thread(executor.run, call)
                    except (KeyError, ValueError) as exc:
                        result = f"error: {exc}"
                    if self._tool_loop_dedupe:
                        executed_cache[key] = result
                yield {
                    "type": "tool_call",
                    "column": column_id,
                    "call_id": call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                yield {
                    "type": "tool_result",
                    "column": column_id,
                    "call_id": call_id,
                    "content": result,
                }
                tool_results.append((call.name, result))
                turns.append({"role": "tool", "name": call.name, "content": result})

            column_messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": [asdict(c) for c in chat.tool_calls],
                }
            )
            for name, content in tool_results:
                column_messages.append({"role": "tool", "name": name, "content": content})

            working_messages = _append_tool_turn_messages(
                working_messages,
                assistant_content=assistant_content,
                tool_calls=chat.tool_calls,
                tool_results=tool_results,
            )
        else:
            exhausted = final_chat is not None and bool(final_chat.tool_calls)

        if final_chat is None:
            yield {"type": "error", "column": column_id, "message": "no chat result"}
            return

        if exhausted:
            final_chat = ChatResult(
                thinking=final_chat.thinking,
                answer=final_chat.answer,
                finish_reason="tool_loop_exhausted",
                prompt_tokens=final_chat.prompt_tokens,
                completion_tokens=final_chat.completion_tokens,
                effective_max_tokens=final_chat.effective_max_tokens,
                tool_calls=final_chat.tool_calls,
                raw_completion=final_chat.raw_completion,
                suspected_unparsed_tool_calls=final_chat.suspected_unparsed_tool_calls,
            )

        yield {
            "type": "_tool_loop_done",
            "final_chat": final_chat,
            "turns": turns,
        }
