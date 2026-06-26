"""チャット SSE ストリーミング (tool loop 含む)。"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from joryu.chat.persistence import build_chat_record
from joryu.chat.session import ChatColumn, ChatSession
from joryu.responses_store import record_id
from joryu.styles import apply_style
from joryu.tool_call_recovery import recover_tool_call
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolExecutor
from joryu.vllm_client import ChatResult, SupportsChat
from joryu.writer import JsonlAppendWriter

DEFAULT_MAX_TURNS = 4
TOKEN_CHUNK_SIZE = 8


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


def _chunk_text(text: str, size: int = TOKEN_CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + size] for i in range(0, len(text), size)]


async def _yield_tokens(column_id: str, text: str) -> AsyncIterator[dict[str, Any]]:
    for chunk in _chunk_text(text):
        yield {"type": "token", "column": column_id, "delta": chunk}


async def stream_column_turn(
    session: ChatSession,
    column: ChatColumn,
    user_text: str,
    *,
    client: SupportsChat,
    sampling: dict[str, Any],
    max_turns: int = DEFAULT_MAX_TURNS,
    tool_loop_dedupe: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """1 列 1 ターン分をストリーム。完了時に JSONL へ 1 行追記。"""
    column_id = column.style_id
    preset = session.style_presets[column_id]
    _style_id, system_prompt = apply_style(session.base_system_prompt, preset)
    turn_index = column.turn_index
    column.messages.append({"role": "user", "content": user_text})

    working_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *column.messages,
    ]
    tools = session.tools or None
    executor: ToolExecutor | None = session.executor
    turns: list[dict[str, Any]] = []
    final_chat: ChatResult | None = None
    exhausted = False
    executed_cache: dict[tuple[str, str], str] = {}

    for _ in range(max_turns):
        chat = client.chat_via_template(
            working_messages,
            enable_thinking=True,
            tools=tools,
            **sampling,
        )
        if tools:
            chat, _recovery = recover_tool_call(
                client,
                chat,
                messages=working_messages,
                tools=tools,
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

        async for tok in _yield_tokens(column_id, chat.answer or ""):
            yield tok

        if not chat.tool_calls or executor is None:
            column.messages.append({"role": "assistant", "content": chat.answer or ""})
            break

        assistant_content = chat.answer or ""
        tool_results: list[tuple[str, str]] = []
        call_ids = [_generate_tool_call_id() for _ in chat.tool_calls]
        for call_id, call in zip(call_ids, chat.tool_calls, strict=True):
            key = _tool_call_dedupe_key(call)
            if tool_loop_dedupe and key in executed_cache:
                result = executed_cache[key]
            else:
                try:
                    result = executor.run(call)
                except (KeyError, ValueError) as exc:
                    result = f"error: {exc}"
                if tool_loop_dedupe:
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

        column.messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [asdict(c) for c in chat.tool_calls],
            }
        )
        for name, content in tool_results:
            column.messages.append({"role": "tool", "name": name, "content": content})

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

    column.turn_index += 1
    final_answer = (final_chat.answer or "").strip()
    record = build_chat_record(
        prompt=user_text,
        style_id=column_id,
        system_prompt=system_prompt,
        session_id=session.session_id,
        turn_index=turn_index,
        thinking=final_chat.thinking,
        answer=final_answer,
        model_name=session.model_name,
        config_hash=session.config_hash,
        chat=final_chat,
        turns=turns,
        sampling=sampling,
        tools=session.tools,
        tool_ids=session.tool_ids,
    )
    with JsonlAppendWriter(session.out_path) as writer:
        writer.write(record)

    yield {
        "type": "column_done",
        "column": column_id,
        "finish_reason": final_chat.finish_reason,
        "record_id": record_id(record),
    }
