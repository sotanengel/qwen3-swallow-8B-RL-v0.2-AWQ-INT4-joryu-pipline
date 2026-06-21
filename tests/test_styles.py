"""styles.py: 文体プリセットの読み込みと system_prompt 合成。"""

from pathlib import Path

import pytest

from joryu.styles import StylePreset, apply_style, load_styles, resolve_style_ids


def test_load_styles_from_repo_default() -> None:
    styles = load_styles(Path("styles.yaml"))
    assert "polite" in styles
    assert styles["polite"].label == "丁寧語"
    assert "です・ます調" in styles["polite"].instruction


def test_apply_style_appends_instruction() -> None:
    preset = StylePreset(style_id="polite", label="丁寧語", instruction="丁寧に答えて。")
    style_id, merged = apply_style("ベース。", preset)
    assert style_id == "polite"
    assert merged.startswith("ベース。")
    assert merged.endswith("丁寧に答えて。")


def test_resolve_style_ids_unknown_raises() -> None:
    styles = load_styles(Path("styles.yaml"))
    with pytest.raises(ValueError, match="unknown style"):
        resolve_style_ids(["polite", "missing"], styles)


def test_resolve_style_ids_returns_presets() -> None:
    styles = load_styles(Path("styles.yaml"))
    resolved = resolve_style_ids(["polite", "casual"], styles)
    assert [p.style_id for p in resolved] == ["polite", "casual"]
