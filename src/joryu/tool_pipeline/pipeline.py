"""Tool call multi-turn パイプライン (#257)。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from joryu.tool_call_recovery import recover_tool_call
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolExecutor
from joryu.tool_pipeline.decision import ToolLoopDecisionMaker
from joryu.vllm.protocol import ChatResult, SupportsChat

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


def append_tool_turn_messages(
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


def tool_call_dedupe_key(call: ParsedToolCall) -> tuple[str, str]:
    return (
        call.name,
        json.dumps(call.arguments, sort_keys=True, ensure_ascii=False),
    )


def aggregate_tool_calls_from_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """tool_loop の各 assistant turn から tool_calls を集約する。"""
    aggregated: list[dict[str, Any]] = []
    for turn in turns:
        if turn.get("role") != "assistant":
            continue
        for call in turn.get("tool_calls") or []:
            if isinstance(call, dict) and isinstance(call.get("name"), str):
                aggregated.append(call)
    return aggregated


class ToolCallPipeline:
    """distill / chat 共通の sync tool loop 実行。"""

    def __init__(
        self,
        *,
        max_turns: int = DEFAULT_MAX_TURNS,
        tool_loop_dedupe: bool = True,
        decision_maker: ToolLoopDecisionMaker | None = None,
    ) -> None:
        self._max_turns = max_turns
        self._tool_loop_dedupe = tool_loop_dedupe
        self._decision = decision_maker or ToolLoopDecisionMaker()

    def run_sync(
        self,
        client: SupportsChat,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        executor: ToolExecutor | None,
        sampling: dict[str, Any],
        no_think_fallback: bool = False,
    ) -> tuple[ChatResult, list[dict[str, Any]], dict[str, int] | None]:
        """tool_call が無くなるか max_turns に達するまで chat を回す。"""
        turns: list[dict[str, Any]] = []
        working_messages = list(messages)
        final_chat: ChatResult | None = None
        exhausted = False
        executed_cache: dict[tuple[str, str], str] = {}
        call_index_by_key: dict[tuple[str, str], int] = {}
        skipped_calls = 0
        unique_calls = 0

        for _turn_index in range(self._max_turns):
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
                    no_think_fallback=no_think_fallback,
                )
            final_chat = chat
            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": chat.answer,
                "tool_calls": [asdict(c) for c in chat.tool_calls],
            }
            if chat.raw_completion is not None:
                assistant_turn["raw_completion"] = chat.raw_completion
            if chat.suspected_unparsed_tool_calls:
                assistant_turn["suspected_unparsed_tool_calls"] = list(
                    chat.suspected_unparsed_tool_calls
                )
            turns.append(assistant_turn)

            if self._decision.should_break_after_chat(chat, has_executor=executor is not None):
                break

            assert executor is not None
            assistant_content = chat.answer or ""
            tool_results: list[tuple[str, str]] = []
            for call in chat.tool_calls:
                deduped = False
                original_call_index: int | None = None
                key = tool_call_dedupe_key(call)
                if self._tool_loop_dedupe and key in executed_cache:
                    result = executed_cache[key]
                    deduped = True
                    original_call_index = call_index_by_key[key]
                    skipped_calls += 1
                else:
                    try:
                        result = executor.run(call)
                    except (KeyError, ValueError) as exc:
                        result = f"error: {exc}"
                    if self._tool_loop_dedupe:
                        executed_cache[key] = result
                        call_index_by_key[key] = unique_calls
                        unique_calls += 1
                tool_results.append((call.name, result))
                tool_turn: dict[str, Any] = {
                    "role": "tool",
                    "name": call.name,
                    "content": result,
                }
                if deduped:
                    tool_turn["deduped"] = True
                    tool_turn["original_call_index"] = original_call_index
                turns.append(tool_turn)
            working_messages = append_tool_turn_messages(
                working_messages,
                assistant_content=assistant_content,
                tool_calls=chat.tool_calls,
                tool_results=tool_results,
            )
        else:
            exhausted = self._decision.is_exhausted(
                loop_completed=True,
                broke_early=False,
                chat=final_chat,
            )

        if final_chat is None:
            raise RuntimeError("chat loop produced no result")

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
        dedupe_meta: dict[str, int] | None = None
        if self._tool_loop_dedupe and (skipped_calls or unique_calls):
            dedupe_meta = {"skipped_calls": skipped_calls, "unique_calls": unique_calls}
        return final_chat, turns, dedupe_meta


__all__ = [
    "DEFAULT_MAX_TURNS",
    "ToolCallPipeline",
    "aggregate_tool_calls_from_turns",
    "append_tool_turn_messages",
    "tool_call_dedupe_key",
]
