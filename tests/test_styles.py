"""styles.py: 文体プリセットの読み込みと system_prompt 合成。"""

from pathlib import Path

import pytest

from joryu.styles import StylePreset, apply_style, load_styles, resolve_style_ids


def test_load_styles_from_repo_default() -> None:
    styles = load_styles(Path("styles.yaml"))
    expected_ids = ("prose", "qa_short", "dialog", "report")
    assert set(styles) == set(expected_ids)
    assert styles["prose"].label == "散文"
    assert "マークダウン記号" in styles["prose"].instruction
    assert styles["qa_short"].label == "短答"
    assert "結論を最初" in styles["qa_short"].instruction
    assert styles["dialog"].label == "対話"
    assert "マークダウン記号" in styles["dialog"].instruction
    assert "2〜4 文" in styles["dialog"].instruction
    assert "短く" in styles["dialog"].instruction
    assert styles["report"].label == "レポート"
    assert "構造化されたレポート" in styles["report"].instruction


def test_resolve_format_axis_style_ids() -> None:
    styles = load_styles(Path("styles.yaml"))
    resolved = resolve_style_ids(["prose", "qa_short", "dialog", "report"], styles)
    assert [p.style_id for p in resolved] == ["prose", "qa_short", "dialog", "report"]


def test_apply_style_appends_instruction() -> None:
    preset = StylePreset(style_id="prose", label="散文", instruction="散文で答えて。")
    style_id, merged = apply_style("ベース。", preset)
    assert style_id == "prose"
    assert merged.startswith("ベース。")
    assert merged.endswith("散文で答えて。")


def test_resolve_style_ids_unknown_raises() -> None:
    styles = load_styles(Path("styles.yaml"))
    with pytest.raises(ValueError, match="unknown style"):
        resolve_style_ids(["prose", "missing"], styles)


def test_resolve_style_ids_returns_presets() -> None:
    styles = load_styles(Path("styles.yaml"))
    resolved = resolve_style_ids(["prose", "dialog"], styles)
    assert [p.style_id for p in resolved] == ["prose", "dialog"]


def test_removed_tone_styles_raise_unknown() -> None:
    """polite/casual/expert は #90 で削除されたため未知スタイル扱い。"""
    styles = load_styles(Path("styles.yaml"))
    for sid in ("polite", "casual", "expert"):
        with pytest.raises(ValueError, match="unknown style"):
            resolve_style_ids([sid], styles)
