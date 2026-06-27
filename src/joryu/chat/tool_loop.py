"""Tool loop 実行。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, replace
from typing import Any

from joryu.chat.thinking_guard import (
    ensure_not_thinking_runaway,
    register_empty_thinking_delta,
    strip_think_blocks,
)
from joryu.chat.token_stream import TokenStreamer
from joryu.completion_normalize import normalize_chat_result
from joryu.tool_call_recovery import recover_tool_call
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolExecutor, ToolUpstreamError
from joryu.tool_pipeline.decision import ToolLoopDecisionMaker
from joryu.tool_pipeline.pipeline import (
    append_tool_turn_messages,
    normalize_tool_arguments,
    tool_call_dedupe_key,
)
from joryu.vllm_client import ChatResult, SupportsChat, SupportsChatStream

DEFAULT_MAX_TURNS = 4
_MAX_REPEAT_TOOL_ERROR = 2
_FINISH_REASON_ERROR = "error"
_TOOL_EXECUTION_TIMEOUT_SEC = 15.0


def _generate_tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"


def _normalize_tool_call(call: ParsedToolCall) -> ParsedToolCall:
    return ParsedToolCall(
        name=call.name,
        arguments=normalize_tool_arguments(call.arguments),
        raw=call.raw,
    )


def _tool_error_fingerprint(name: str, result: str) -> tuple[str, str]:
    return (name, result)


def _sanitize_chat_result(chat: ChatResult) -> ChatResult:
    sanitized = strip_think_blocks(chat.answer or "")
    if sanitized == chat.answer:
        return chat
    return replace(chat, answer=sanitized)


def _sanitize_assistant_content(content: str) -> str:
    return strip_think_blocks(content or "")


def _error_chat_result() -> ChatResult:
    return ChatResult(
        thinking=None,
        answer="",
        finish_reason=_FINISH_REASON_ERROR,
        prompt_tokens=0,
        completion_tokens=0,
        effective_max_tokens=None,
        tool_calls=(),
        raw_completion=None,
        suspected_unparsed_tool_calls=(),
    )


async def _execute_tool_call(
    executor: ToolExecutor,
    call: ParsedToolCall,
    *,
    cancel_event: asyncio.Event | None,
    timeout: float = _TOOL_EXECUTION_TIMEOUT_SEC,
) -> str:
    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError("client disconnected, cancelling tool task")

    async def _run() -> str:
        task = asyncio.create_task(asyncio.to_thread(executor.run, call))
        try:
            while not task.done():
                if cancel_event and cancel_event.is_set():
                    task.cancel()
                    raise asyncio.CancelledError("client disconnected, cancelling tool task")
                await asyncio.wait({task}, timeout=0.25)
            return task.result()
        finally:
            if not task.done():
                task.cancel()

    return await asyncio.wait_for(_run(), timeout=timeout)


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
        self._decision = ToolLoopDecisionMaker()

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
        empty_think_streak = 0
        async for chunk in stream_client.chat_stream(
            working_messages,
            enable_thinking=True,
            tools=tools_arg,
            **sampling,
        ):
            kind = getattr(chunk, "kind", None)
            if kind == "content" and chunk.delta:
                empty_think_streak = register_empty_thinking_delta(
                    delta=chunk.delta,
                    streak=empty_think_streak,
                )
                ensure_not_thinking_runaway(empty_think_streak)
                if empty_think_streak:
                    continue
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
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        final_chat: ChatResult | None = None
        exhausted = False
        executed_cache: dict[tuple[str, str], str] = {}
        error_fingerprint_counts: dict[tuple[str, str], int] = {}
        abort_tool_loop = False
        tools_arg = tools or None
        tool_loop_done_emitted = False
        error_emitted = False

        try:
            for turn_index in range(self._max_turns):
                if abort_tool_loop:
                    exhausted = True
                    break
                yield {
                    "type": "turn_start",
                    "column": column_id,
                    "turn": turn_index + 1,
                }

                try:
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
                            yield {
                                "type": "error",
                                "column": column_id,
                                "message": "no chat result",
                            }
                            error_emitted = True
                            final_chat = None
                            break
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
                        chat = normalize_chat_result(chat, tools=tools_arg)
                        chat, _recovery = await asyncio.to_thread(
                            recover_tool_call,
                            client,
                            chat,
                            messages=working_messages,
                            tools=tools_arg,
                            sampling=sampling,
                        )
                    else:
                        chat = normalize_chat_result(chat, tools=None)
                    final_chat = chat

                    assistant_turn: dict[str, Any] = {
                        "role": "assistant",
                        "content": _sanitize_assistant_content(chat.answer or ""),
                        "tool_calls": [asdict(c) for c in chat.tool_calls],
                    }
                    if chat.raw_completion is not None:
                        assistant_turn["raw_completion"] = chat.raw_completion
                    turns.append(assistant_turn)

                    if self._decision.should_break_after_chat(
                        chat,
                        has_executor=executor is not None,
                    ):
                        column_messages.append(
                            {
                                "role": "assistant",
                                "content": _sanitize_assistant_content(chat.answer or ""),
                            }
                        )
                        break

                    assistant_content = _sanitize_assistant_content(chat.answer or "")
                    tool_results: list[tuple[str, str]] = []
                    call_ids = [_generate_tool_call_id() for _ in chat.tool_calls]
                    for call_id, call in zip(call_ids, chat.tool_calls, strict=True):
                        normalized_call = _normalize_tool_call(call)
                        key = tool_call_dedupe_key(normalized_call)
                        tool_error: dict[str, Any] | None = None
                        repeated_error_result: str | None = None
                        for (tool_name, err_result), count in error_fingerprint_counts.items():
                            if (
                                tool_name == normalized_call.name
                                and count >= _MAX_REPEAT_TOOL_ERROR
                            ):
                                repeated_error_result = err_result
                                break
                        if self._tool_loop_dedupe and key in executed_cache:
                            result = executed_cache[key]
                        elif repeated_error_result is not None:
                            result = repeated_error_result
                        else:
                            try:
                                result = await _execute_tool_call(
                                    executor,
                                    normalized_call,
                                    cancel_event=cancel_event,
                                )
                            except asyncio.CancelledError:
                                raise
                            except ToolUpstreamError as exc:
                                result = f"error: HTTP {exc.status} — {exc.body}"
                                tool_error = {
                                    "type": "tool_error",
                                    "column": column_id,
                                    "call_id": call_id,
                                    "name": normalized_call.name,
                                    "message": str(exc),
                                    "status": exc.status,
                                    "body": exc.body,
                                }
                            except Exception as exc:
                                result = f"error: {exc}"
                                tool_error = {
                                    "type": "tool_error",
                                    "column": column_id,
                                    "call_id": call_id,
                                    "name": normalized_call.name,
                                    "message": str(exc),
                                }
                            if self._tool_loop_dedupe:
                                executed_cache[key] = result
                        if result.startswith("error:"):
                            if tool_error is None:
                                tool_error = {
                                    "type": "tool_error",
                                    "column": column_id,
                                    "call_id": call_id,
                                    "name": normalized_call.name,
                                    "message": result.removeprefix("error: "),
                                }
                            fp = _tool_error_fingerprint(normalized_call.name, result)
                            error_fingerprint_counts[fp] = error_fingerprint_counts.get(fp, 0) + 1
                            if error_fingerprint_counts[fp] >= _MAX_REPEAT_TOOL_ERROR:
                                abort_tool_loop = True
                        yield {
                            "type": "tool_call",
                            "column": column_id,
                            "call_id": call_id,
                            "name": normalized_call.name,
                            "arguments": normalized_call.arguments,
                        }
                        if tool_error is not None:
                            yield tool_error
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

                    working_messages = append_tool_turn_messages(
                        working_messages,
                        assistant_content=assistant_content,
                        tool_calls=chat.tool_calls,
                        tool_results=tool_results,
                    )
                except asyncio.CancelledError:
                    yield {
                        "type": "error",
                        "column": column_id,
                        "message": "client disconnected, cancelling tool task",
                    }
                    error_emitted = True
                    break
                except Exception as exc:
                    yield {"type": "error", "column": column_id, "message": str(exc)}
                    error_emitted = True
                    break
            else:
                exhausted = self._decision.is_exhausted(
                    loop_completed=True,
                    broke_early=False,
                    chat=final_chat,
                )

            if final_chat is None and not error_emitted:
                yield {"type": "error", "column": column_id, "message": "no chat result"}

            if exhausted and final_chat is not None:
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

            if final_chat is not None:
                final_chat = _sanitize_chat_result(final_chat)
                yield {
                    "type": "_tool_loop_done",
                    "final_chat": final_chat,
                    "turns": turns,
                }
                tool_loop_done_emitted = True
        finally:
            if not tool_loop_done_emitted:
                if final_chat is None:
                    final_chat = _error_chat_result()
                else:
                    final_chat = _sanitize_chat_result(final_chat)
                yield {
                    "type": "_tool_loop_done",
                    "final_chat": final_chat,
                    "turns": turns,
                }
