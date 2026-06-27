"""ChatResult の tool_call 抽出・thinking サニタイズ (#220)。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from joryu.tool_calls import ParsedToolCall, extract_tool_calls_with_diagnostics

if TYPE_CHECKING:
    from joryu.vllm_client import ChatResult

_META_INSTRUCTION_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"For each function call[^.\n]*\.?"
    r"|return a json object with function name and arguments[^.\n]*\.?"
    r"|You should call the function[^.\n]*\.?"
    r")"
    r"\s*",
)


def sanitize_thinking_trace(text: str | None) -> str | None:
    """thinking から chat_template 由来の英語メタ命令断片を除去する。"""
    if text is None:
        return None
    cleaned = _META_INSTRUCTION_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or None


def _merge_hints(*hint_lists: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for hints in hint_lists:
        for hint in hints:
            if hint not in seen:
                merged.append(hint)
                seen.add(hint)
            if len(merged) >= 5:
                return tuple(merged)
    return tuple(merged)


def _extract_from_text(
    text: str,
    *,
    known_tool_names: set[str] | None,
) -> tuple[tuple[ParsedToolCall, ...], str, tuple[str, ...]]:
    calls, cleaned, diagnostics = extract_tool_calls_with_diagnostics(
        text,
        known_tool_names=known_tool_names,
    )
    hints = tuple(diagnostics.get("suspected_unparsed_tool_calls", []))
    return tuple(calls), cleaned, hints


def normalize_chat_result(
    chat: ChatResult,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    """answer / thinking から tool_call を抽出し ChatResult を正規化する。

    OpenAI streaming 経路で bare JSON が answer に残るケース (#229) や、
    2 周目以降の JSON 再生成 (#233) を救済する。
    """
    from joryu.vllm_client import ChatResult, extract_known_tool_names

    known = extract_known_tool_names(tools)
    known_set = known or None

    thinking = sanitize_thinking_trace(chat.thinking)
    answer = (chat.answer or "").strip()

    existing_calls = tuple(chat.tool_calls)
    all_hints: list[tuple[str, ...]] = []

    if existing_calls:
        final_calls = existing_calls
        _, cleaned_answer, hints = _extract_from_text(answer, known_tool_names=known_set)
        answer = cleaned_answer
        all_hints.append(hints)
        if thinking:
            _, cleaned_thinking, think_hints = _extract_from_text(
                thinking,
                known_tool_names=known_set,
            )
            thinking = cleaned_thinking or None
            all_hints.append(think_hints)
    else:
        answer_calls, answer, answer_hints = _extract_from_text(answer, known_tool_names=known_set)
        think_calls: tuple[ParsedToolCall, ...] = ()
        think_hints: tuple[str, ...] = ()
        if thinking:
            think_calls, thinking, think_hints = _extract_from_text(
                thinking,
                known_tool_names=known_set,
            )
            thinking = thinking or None
        final_calls = answer_calls or think_calls
        all_hints.extend([answer_hints, think_hints])

        if not final_calls and chat.raw_completion:
            raw_calls, _, raw_hints = _extract_from_text(
                chat.raw_completion,
                known_tool_names=known_set,
            )
            if raw_calls:
                final_calls = raw_calls
            elif raw_hints:
                all_hints.append(raw_hints)

    suspected = _merge_hints(*all_hints)
    if not final_calls and not suspected and chat.suspected_unparsed_tool_calls:
        suspected = chat.suspected_unparsed_tool_calls

    return ChatResult(
        thinking=thinking,
        answer=answer,
        finish_reason=chat.finish_reason,
        prompt_tokens=chat.prompt_tokens,
        completion_tokens=chat.completion_tokens,
        effective_max_tokens=chat.effective_max_tokens,
        tool_calls=final_calls,
        raw_completion=chat.raw_completion,
        suspected_unparsed_tool_calls=suspected,
    )


__all__ = ["normalize_chat_result", "sanitize_thinking_trace"]
