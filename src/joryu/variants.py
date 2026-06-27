"""バリアント直積展開: style × temperature × top_p。"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from joryu.config import Config
from joryu.prompt_bank import EffectiveSampling, PromptRow, merge_with_defaults
from joryu.styles import StylePreset
from joryu.system_prompt import build_system_prompt
from joryu.tools import ToolDefinition, resolve_tool_ids


@dataclass
class DistillVariant:
    """1 回の蒸留実行単位（prompt + 解決済み sampling/style）。"""

    row: PromptRow
    eff: EffectiveSampling


def parse_comma_list(text: str | None) -> list[str]:
    """カンマ区切り文字列をトリムして分割。空は []。"""
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_float_list(
    text: str | None,
    *,
    min_val: float,
    max_val: float,
    name: str,
) -> list[float] | None:
    """カンマ区切り float リスト。空/None は None（スイープなし）。"""
    if not text:
        return None
    parts = parse_comma_list(text)
    if not parts:
        return None
    values: list[float] = []
    for part in parts:
        try:
            val = float(part)
        except ValueError as exc:
            raise ValueError(f"invalid {name} value {part!r}") from exc
        if val < min_val or val > max_val:
            raise ValueError(f"{name} must be in [{min_val}, {max_val}], got {val}")
        values.append(val)
    return values


def expand_variants(
    rows: list[PromptRow],
    cfg: Config,
    *,
    style_presets: list[StylePreset] | None = None,
    temperatures: list[float] | None = None,
    top_ps: list[float] | None = None,
    tools_registry: dict[str, ToolDefinition] | None = None,
) -> list[DistillVariant]:
    """prompt bank 行を style × temperature × top_p の直積で展開する。

    CLI 未指定の軸は merge 後の単一値を使用（style 未指定時は style_id=None）。
    mode 軸は #94 で削除済み (常に thinking 固定で運用)。
    """
    style_list: list[StylePreset | None] = list(style_presets) if style_presets else [None]
    variants: list[DistillVariant] = []

    for row in rows:
        base_eff = merge_with_defaults(row, cfg, tools_registry=tools_registry)
        temp_axis = temperatures if temperatures is not None else [base_eff.sampling["temperature"]]
        top_p_axis = top_ps if top_ps is not None else [base_eff.sampling["top_p"]]

        for preset in style_list:
            for temp in temp_axis:
                for top_p in top_p_axis:
                    eff = copy.deepcopy(base_eff)
                    eff.sampling = dict(eff.sampling)
                    eff.sampling["temperature"] = temp
                    eff.sampling["top_p"] = top_p

                    tool_defs: list[ToolDefinition] = []
                    if row.tool_ids and tools_registry:
                        tool_defs = resolve_tool_ids(row.tool_ids, tools_registry)
                    elif tools_registry and eff.tools:
                        for schema in eff.tools:
                            fn = schema.get("function") if isinstance(schema, dict) else None
                            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                                name = fn["name"]
                                if name in tools_registry:
                                    tool_defs.append(tools_registry[name])

                    if preset is not None:
                        eff.system_prompt = build_system_prompt(
                            base=eff.system_prompt,
                            tool_defs=tool_defs or None,
                            style_preset=preset,
                        )
                        eff.style_id = preset.style_id
                    elif tool_defs:
                        eff.system_prompt = build_system_prompt(
                            base=eff.system_prompt,
                            tool_defs=tool_defs,
                        )
                    elif row.style_id is not None:
                        eff.style_id = row.style_id

                    variants.append(DistillVariant(row=row, eff=eff))

    return variants
