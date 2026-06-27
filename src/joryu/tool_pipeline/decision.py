"""Tool loop 終了条件の一元化 (#257)。"""

from __future__ import annotations

from joryu.vllm.protocol import ChatResult


class ToolLoopDecisionMaker:
    """max_turns / empty calls / exhausted を判定する。"""

    def should_break_after_chat(
        self,
        chat: ChatResult,
        *,
        has_executor: bool,
    ) -> bool:
        """tool 実行なしでループを抜けるか。"""
        return not chat.tool_calls or not has_executor

    def is_exhausted(
        self,
        *,
        loop_completed: bool,
        broke_early: bool,
        chat: ChatResult | None,
    ) -> bool:
        """max_turns 到達時に tool_calls が残っているか。"""
        if broke_early or chat is None:
            return False
        return loop_completed and bool(chat.tool_calls)


__all__ = ["ToolLoopDecisionMaker"]
