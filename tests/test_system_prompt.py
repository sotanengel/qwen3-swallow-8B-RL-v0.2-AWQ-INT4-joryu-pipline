"""system_prompt.py のユニットテスト。"""

from __future__ import annotations

from joryu.styles import StylePreset
from joryu.system_prompt import build_system_prompt
from joryu.tools import ToolDefinition


def test_build_system_prompt_style_is_last() -> None:
    preset = StylePreset(
        style_id="prose",
        label="散文",
        instruction="マークダウン記号や箇条書き、表は使わず、一段落で答えてください。",
    )
    tool = ToolDefinition(
        name="weather",
        description="天気",
        parameters={"type": "object", "properties": {}},
        invocation_rule="天気を尋ねられたら必ず呼ぶ。",
    )
    prompt = build_system_prompt(
        base="あなたは丁寧なアシスタントです。",
        tool_defs=[tool],
        style_preset=preset,
    )
    assert prompt.endswith(preset.instruction)
    style_pos = prompt.index(preset.instruction)
    tool_pos = prompt.index("利用可能なツール:")
    assert tool_pos < style_pos


def test_build_system_prompt_includes_factual_guard() -> None:
    prompt = build_system_prompt(base="base", factual_guard=True)
    assert "仮想データ" in prompt
    assert "ツール経由" in prompt
