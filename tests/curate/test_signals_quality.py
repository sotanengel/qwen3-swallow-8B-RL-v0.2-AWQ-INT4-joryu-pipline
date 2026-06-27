"""quality.py R-10 シグナルのテスト。"""

from __future__ import annotations

from joryu.curate.signals.quality import (
    FactualHallucination,
    StyleFormat,
    ToolLeak,
    VirtualData,
)


def _rec(**overrides):
    base = {"prompt": "p", "answer": "あ" * 50, "tools": [], "tool_calls": []}
    base.update(overrides)
    return base


def test_tool_leak_rejects_suspected_hints() -> None:
    sig = ToolLeak()
    r = sig.evaluate(_rec(suspected_unparsed_tool_calls=['{"name": "weather"}']))
    assert r.hard_reject is True


def test_factual_hallucination_rejects_numeric_without_tool_call() -> None:
    sig = FactualHallucination()
    r = sig.evaluate(
        _rec(
            tools=[{"type": "function", "function": {"name": "weather"}}],
            tool_calls=[],
            answer="今日は晴れで最高気温28℃です。",
        )
    )
    assert r.hard_reject is True


def test_factual_hallucination_ok_with_tool_calls() -> None:
    sig = FactualHallucination()
    r = sig.evaluate(
        _rec(
            tools=[{"type": "function", "function": {"name": "weather"}}],
            tool_calls=[{"name": "weather", "arguments": {}}],
            answer="今日は晴れで最高気温28℃です。",
        )
    )
    assert r.hard_reject is False


def test_virtual_data_rejects_placeholder_phrase() -> None:
    sig = VirtualData()
    r = sig.evaluate(_rec(answer="取得結果（仮想データ）として28℃です。"))
    assert r.hard_reject is True


def test_style_format_rejects_markdown_in_prose() -> None:
    sig = StyleFormat()
    r = sig.evaluate(
        _rec(
            style_id="prose",
            answer='{"name": "weather", "arguments": {}}',
        )
    )
    assert r.hard_reject is False  # JSON alone without markdown markers

    r2 = sig.evaluate(
        _rec(
            style_id="prose",
            answer="- 箇条書き項目\n- 二つ目",
        )
    )
    assert r2.hard_reject is True
