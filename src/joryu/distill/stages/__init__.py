"""Tool loop / recovery Stage (#251)。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from joryu.distill.protocol import DistillContext
from joryu.distill.record import record_from_chat
from joryu.tool_call_recovery import recover_tool_call
from joryu.tool_executor import ToolExecutor
from joryu.tool_pipeline.pipeline import ToolCallPipeline, aggregate_tool_calls_from_turns
from joryu.vllm.protocol import ChatResult, SupportsChat


def make_tool_loop_chat_fn(
    client: SupportsChat,
    executor: ToolExecutor,
    max_turns: int,
    turns_holder: dict[str, Any],
    *,
    no_think_fallback: bool = False,
    tool_loop_dedupe: bool = True,
) -> Callable[..., ChatResult]:
    def _chat_with_loop(
        loop_messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None,
        **sampling_kwargs: Any,
    ) -> ChatResult:
        chat, turns, dedupe_meta = ToolCallPipeline(
            max_turns=max_turns,
            tool_loop_dedupe=tool_loop_dedupe,
        ).run_sync(
            client,
            loop_messages,
            tools=tools,
            executor=executor,
            sampling=sampling_kwargs,
            no_think_fallback=no_think_fallback,
        )
        turns_holder["turns"] = turns
        if dedupe_meta is not None:
            turns_holder["tool_loop_dedupe"] = dedupe_meta
        else:
            turns_holder.pop("tool_loop_dedupe", None)
        return chat

    return _chat_with_loop


def make_build_with_turns(
    build_record: Callable[[ChatResult], dict[str, Any]],
    *,
    use_tool_loop: bool,
    turns_holder: dict[str, Any],
    client: SupportsChat | None = None,
    messages: list[dict[str, str]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    sampling: dict[str, Any] | None = None,
    no_think_fallback: bool = False,
) -> Callable[[ChatResult], dict[str, Any]]:
    def _build_with_turns(chat: ChatResult) -> dict[str, Any]:
        final_chat = chat
        recovery_meta: dict[str, Any] | None = None
        if client is not None and messages is not None and sampling is not None:
            final_chat, recovery_meta = recover_tool_call(
                client,
                chat,
                messages=messages,
                tools=tools,
                sampling=sampling,
                no_think_fallback=no_think_fallback,
            )
        record = build_record(final_chat)
        if recovery_meta and recovery_meta.get("attempts"):
            record["tool_call_recovery"] = recovery_meta
        record["no_think_fallback_used"] = bool(
            recovery_meta.get("no_think_fallback_used") if recovery_meta else False
        )
        if use_tool_loop:
            record["turns"] = turns_holder["turns"]
            aggregated = aggregate_tool_calls_from_turns(turns_holder["turns"])
            if aggregated:
                record["tool_calls"] = aggregated
            if dedupe_meta := turns_holder.get("tool_loop_dedupe"):
                record["tool_loop_dedupe"] = dedupe_meta
        return record

    return _build_with_turns


class RecoveryStage:
    """tool_call_recovery メタを record に付与する Stage。"""

    def process(self, record: dict[str, Any], context: DistillContext) -> dict[str, Any]:
        del context
        return record


class LoopStage:
    """tool_loop turns / dedupe メタを record に反映する Stage。"""

    def process(self, record: dict[str, Any], context: DistillContext) -> dict[str, Any]:
        if not context.use_tool_loop:
            return record
        turns = context.turns_holder.get("turns") or []
        record["turns"] = turns
        aggregated = aggregate_tool_calls_from_turns(turns)
        if aggregated:
            record["tool_calls"] = aggregated
        if dedupe_meta := context.turns_holder.get("tool_loop_dedupe"):
            record["tool_loop_dedupe"] = dedupe_meta
        return record


def build_record_fn(context: DistillContext) -> Callable[[ChatResult], dict[str, Any]]:
    return lambda chat: record_from_chat(
        chat,
        row=context.row,
        eff=context.eff,
        model_name=context.model_name,
        config_hash=context.config_hash,
    )


__all__ = [
    "LoopStage",
    "RecoveryStage",
    "build_record_fn",
    "make_build_with_turns",
    "make_tool_loop_chat_fn",
]
