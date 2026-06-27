"""ToolCallPipeline / ToolLoopDecisionMaker 単体テスト (#257)。"""

from __future__ import annotations

from joryu.tool_calls import ParsedToolCall
from joryu.tool_pipeline.decision import ToolLoopDecisionMaker
from joryu.tool_pipeline.pipeline import ToolCallPipeline
from joryu.tool_pipeline.state import ToolCallState
from joryu.vllm.protocol import ChatResult


def test_tool_loop_decision_maker_breaks_on_empty_calls() -> None:
    dm = ToolLoopDecisionMaker()
    chat = ChatResult(
        thinking=None,
        answer="done",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
    )
    assert dm.should_break_after_chat(chat, has_executor=True) is True


def test_tool_loop_decision_maker_continues_with_tool_calls() -> None:
    dm = ToolLoopDecisionMaker()
    call = ParsedToolCall(name="search", arguments={"q": "x"}, raw="{}")
    chat = ChatResult(
        thinking=None,
        answer="",
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(call,),
    )
    assert dm.should_break_after_chat(chat, has_executor=True) is False


def test_tool_loop_decision_maker_exhausted_when_loop_completes() -> None:
    dm = ToolLoopDecisionMaker()
    call = ParsedToolCall(name="search", arguments={}, raw="{}")
    chat = ChatResult(
        thinking=None,
        answer="",
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(call,),
    )
    assert dm.is_exhausted(loop_completed=True, broke_early=False, chat=chat) is True
    assert dm.is_exhausted(loop_completed=True, broke_early=True, chat=chat) is False


def test_tool_call_state_tracks_turn() -> None:
    state = ToolCallState(
        parsed=(ParsedToolCall(name="a", arguments={}, raw="{}"),),
        loop_turn=2,
        finish_reason=None,
    )
    assert state.loop_turn == 2


def test_tool_call_pipeline_sync_runs_until_no_tools() -> None:
    calls = [
        ParsedToolCall(name="search", arguments={"q": "x"}, raw="{}"),
    ]

    class _Client:
        def __init__(self) -> None:
            self._n = 0

        def chat_via_template(self, messages, **kwargs):
            del messages, kwargs
            self._n += 1
            if self._n == 1:
                return ChatResult(
                    thinking=None,
                    answer="",
                    finish_reason="tool_calls",
                    prompt_tokens=1,
                    completion_tokens=1,
                    tool_calls=tuple(calls),
                )
            return ChatResult(
                thinking=None,
                answer="final",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(),
            )

    class _Executor:
        def run(self, call: ParsedToolCall) -> str:
            return f"ok:{call.name}"

    pipeline = ToolCallPipeline(max_turns=4, tool_loop_dedupe=True)
    chat, turns, dedupe = pipeline.run_sync(
        _Client(),
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        executor=_Executor(),
        sampling={"temperature": 0.7},
    )
    assert chat.answer == "final"
    assert len(turns) >= 2
    assert dedupe is not None
    assert dedupe["unique_calls"] == 1


def test_tool_call_pipeline_exhausted_at_max_turns() -> None:
    call = ParsedToolCall(name="search", arguments={"q": "x"}, raw="{}")

    class _Client:
        def chat_via_template(self, messages, **kwargs):
            del messages, kwargs
            return ChatResult(
                thinking=None,
                answer="",
                finish_reason="tool_calls",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(call,),
            )

    class _Executor:
        def run(self, call: ParsedToolCall) -> str:
            return "ok"

    pipeline = ToolCallPipeline(max_turns=1, tool_loop_dedupe=False)
    chat, _turns, _dedupe = pipeline.run_sync(
        _Client(),
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        executor=_Executor(),
        sampling={},
    )
    assert chat.finish_reason == "tool_loop_exhausted"


def test_tool_call_pipeline_dedupes_repeated_calls() -> None:
    call = ParsedToolCall(name="search", arguments={"q": "x"}, raw="{}")

    class _Client:
        def __init__(self) -> None:
            self._n = 0

        def chat_via_template(self, messages, **kwargs):
            del messages, kwargs
            self._n += 1
            if self._n <= 2:
                return ChatResult(
                    thinking=None,
                    answer="",
                    finish_reason="tool_calls",
                    prompt_tokens=1,
                    completion_tokens=1,
                    tool_calls=(call,),
                )
            return ChatResult(
                thinking=None,
                answer="done",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                tool_calls=(),
            )

    class _Executor:
        def __init__(self) -> None:
            self.count = 0

        def run(self, call: ParsedToolCall) -> str:
            self._ = call
            self.count += 1
            return "result"

    executor = _Executor()
    pipeline = ToolCallPipeline(max_turns=4, tool_loop_dedupe=True)
    _chat, turns, dedupe = pipeline.run_sync(
        _Client(),
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        executor=executor,
        sampling={},
    )
    assert executor.count == 1
    assert dedupe is not None
    assert dedupe["skipped_calls"] >= 1
    tool_turns = [t for t in turns if t.get("role") == "tool" and t.get("deduped")]
    assert tool_turns
