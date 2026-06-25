"""variants.py: バリアント直積展開と sampling パース。"""

import pytest

from joryu.config import Config
from joryu.prompt_bank import PromptRow
from joryu.styles import StylePreset, load_styles
from joryu.variants import (
    DistillVariant,
    expand_variants,
    parse_comma_list,
    parse_float_list,
)


def test_parse_float_list_empty_returns_none() -> None:
    assert parse_float_list("", min_val=0.5, max_val=1.0, name="temperature") is None
    assert parse_float_list(None, min_val=0.5, max_val=1.0, name="temperature") is None  # type: ignore[arg-type]


def test_parse_float_list_parses_values() -> None:
    assert parse_float_list("0.5,0.7,1.0", min_val=0.5, max_val=1.0, name="temperature") == [
        0.5,
        0.7,
        1.0,
    ]


def test_parse_float_list_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="temperature"):
        parse_float_list("0.4", min_val=0.5, max_val=1.0, name="temperature")


def test_parse_comma_list() -> None:
    assert parse_comma_list("prose,dialog") == ["prose", "dialog"]
    assert parse_comma_list("") == []


def test_expand_variants_cartesian_product() -> None:
    cfg = Config()
    rows = [PromptRow(prompt="P1")]
    styles = load_styles("styles.yaml")
    prose = styles["prose"]
    dialog = styles["dialog"]
    variants = expand_variants(
        rows,
        cfg,
        style_presets=[prose, dialog],
        temperatures=[0.5, 0.8],
        top_ps=[0.8, 0.9],
    )
    assert len(variants) == 8  # 2 styles × 2 temps × 2 top_p
    assert all(isinstance(v, DistillVariant) for v in variants)
    temps = {v.eff.sampling["temperature"] for v in variants}
    top_ps = {v.eff.sampling["top_p"] for v in variants}
    style_ids = {v.eff.style_id for v in variants}
    assert temps == {0.5, 0.8}
    assert top_ps == {0.8, 0.9}
    assert style_ids == {"prose", "dialog"}


def test_expand_variants_no_cli_uses_single_defaults() -> None:
    cfg = Config()
    rows = [PromptRow(prompt="P1")]
    variants = expand_variants(rows, cfg)
    assert len(variants) == 1
    assert variants[0].eff.style_id is None
    assert variants[0].eff.sampling["temperature"] == cfg.model.temperature


def test_expand_variants_row_sampling_preserved_when_no_cli_sweep() -> None:
    cfg = Config()
    rows = [PromptRow(prompt="P1", sampling={"temperature": 0.42})]
    variants = expand_variants(rows, cfg)
    assert variants[0].eff.sampling["temperature"] == pytest.approx(0.42)


def test_expand_variants_cli_temperature_overrides_row() -> None:
    cfg = Config()
    rows = [PromptRow(prompt="P1", sampling={"temperature": 0.42})]
    variants = expand_variants(rows, cfg, temperatures=[0.7])
    assert len(variants) == 1
    assert variants[0].eff.sampling["temperature"] == pytest.approx(0.7)


def test_expand_variants_applies_style_to_system_prompt() -> None:
    cfg = Config()
    rows = [PromptRow(prompt="P1")]
    preset = StylePreset(style_id="prose", label="散文", instruction="散文で。")
    variants = expand_variants(rows, cfg, style_presets=[preset])
    assert "散文で。" in variants[0].eff.system_prompt
    assert variants[0].eff.style_id == "prose"


def test_expand_variants_resolves_tools_registry() -> None:
    from joryu.tools import load_tools

    cfg = Config()
    rows = [PromptRow(prompt="P1", tool_ids=["search"])]
    reg = load_tools("tools.yaml")
    variants = expand_variants(rows, cfg, tools_registry=reg)
    assert len(variants) == 1
    assert variants[0].eff.tools[0]["function"]["name"] == "search"
