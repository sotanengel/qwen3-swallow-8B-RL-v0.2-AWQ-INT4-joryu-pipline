"""文体プリセット (styles.yaml) の読み込みと system_prompt 合成。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from joryu.yaml_util import load_yaml_mapping


@dataclass(frozen=True)
class StylePreset:
    style_id: str
    label: str
    instruction: str


def load_styles(path: str | Path) -> dict[str, StylePreset]:
    """styles.yaml からプリセット辞書を読み込む。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"styles file not found: {p}")
    raw = load_yaml_mapping(p)
    styles_raw = raw.get("styles") or {}
    if not isinstance(styles_raw, dict):
        raise ValueError("styles.yaml: 'styles' must be a mapping")
    out: dict[str, StylePreset] = {}
    for style_id, body in styles_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"styles.yaml: style {style_id!r} must be a mapping")
        label = body.get("label") or style_id
        instruction = body.get("instruction")
        if not instruction or not isinstance(instruction, str):
            raise ValueError(f"styles.yaml: style {style_id!r} missing 'instruction'")
        out[style_id] = StylePreset(
            style_id=str(style_id),
            label=str(label),
            instruction=instruction.strip(),
        )
    return out


def resolve_style_ids(style_ids: list[str], styles: dict[str, StylePreset]) -> list[StylePreset]:
    """CLI で指定された style ID をプリセットに解決。未知 ID は ValueError。"""
    resolved: list[StylePreset] = []
    for sid in style_ids:
        if sid not in styles:
            known = ", ".join(sorted(styles))
            raise ValueError(f"unknown style {sid!r}; known styles: {known}")
        resolved.append(styles[sid])
    return resolved


def apply_style(base_system_prompt: str, preset: StylePreset) -> tuple[str, str]:
    """ベース system_prompt の末尾に文体 instruction を追記する。"""
    base = base_system_prompt.rstrip()
    merged = f"{base}\n\n{preset.instruction}" if base else preset.instruction
    return preset.style_id, merged
