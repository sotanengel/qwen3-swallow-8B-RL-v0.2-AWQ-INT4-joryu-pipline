"""system プロンプト合成 (#220 / #234, #231)。"""

from __future__ import annotations

from joryu.prompt_bank import format_tool_usage_hint
from joryu.styles import StylePreset
from joryu.tools import ToolDefinition

_FACTUAL_GUARD = (
    "天気・気温・統計などの事実情報や固有数値は、必ずツール経由で取得してください。"
    "推測値・架空値・「仮想データ」を記載しないでください。"
    "ツールで取得できない場合は、その旨を正直に伝えてください。"
)


def build_system_prompt(
    *,
    base: str,
    tool_defs: list[ToolDefinition] | None = None,
    style_preset: StylePreset | None = None,
    factual_guard: bool = True,
) -> str:
    """合成順: base → factual guard → tool hint → style instruction（最後）。"""
    parts: list[str] = []
    base_stripped = base.rstrip()
    if base_stripped:
        parts.append(base_stripped)
    if factual_guard:
        parts.append(_FACTUAL_GUARD)
    if tool_defs:
        parts.append(format_tool_usage_hint(tool_defs))
    if style_preset is not None:
        parts.append(style_preset.instruction.strip())
    return "\n\n".join(parts)


__all__ = ["build_system_prompt", "_FACTUAL_GUARD"]
