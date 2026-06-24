"""styles.py: 文体プリセットの読み込みと system_prompt 合成。"""

from pathlib import Path

import pytest

from joryu.styles import StylePreset, apply_style, load_styles, resolve_style_ids


def test_load_styles_from_repo_default() -> None:
    styles = load_styles(Path("styles.yaml"))
    expected_ids = ("polite", "casual", "expert", "prose", "qa_short", "dialog", "report")
    assert set(styles) == set(expected_ids)
    assert styles["polite"].label == "丁寧語"
    assert "です・ます調" in styles["polite"].instruction
    assert styles["prose"].label == "散文"
    assert "マークダウン記号" in styles["prose"].instruction
    assert styles["qa_short"].label == "短答"
    assert "結論を最初" in styles["qa_short"].instruction
    assert styles["dialog"].label == "対話"
    assert "会話のように" in styles["dialog"].instruction
    assert styles["report"].label == "レポート"
    assert "構造化されたレポート" in styles["report"].instruction


def test_resolve_format_axis_style_ids() -> None:
    styles = load_styles(Path("styles.yaml"))
    resolved = resolve_style_ids(["prose", "qa_short", "casual", "expert"], styles)
    assert [p.style_id for p in resolved] == ["prose", "qa_short", "casual", "expert"]


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
