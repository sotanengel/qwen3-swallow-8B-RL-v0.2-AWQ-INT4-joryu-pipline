"""prompt_bank.py: JSONL プロンプトバンクの読み取り・上書きマージ・バリデーション。"""

from pathlib import Path

import pytest

from joryu.config import Config
from joryu.prompt_bank import EffectiveSampling, PromptRow, load_prompt_bank, merge_with_defaults


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_minimal_row_uses_defaults(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"prompt": "桜の特徴は？"}'])
    rows = load_prompt_bank(p)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, PromptRow)
    assert row.prompt == "桜の特徴は？"
    assert row.category is None
    assert row.style_id is None
    assert row.sampling == {}
    assert row.system_prompt is None


def test_full_row_carries_overrides(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(
        p,
        [
            (
                '{"prompt":"p","category":"国語","style_id":"essay",'
                '"system_prompt":"sys",'
                '"sampling":{"temperature":0.2,"top_p":0.8,"max_tokens":1024}}'
            )
        ],
    )
    row = load_prompt_bank(p)[0]
    assert row.category == "国語"
    assert row.style_id == "essay"
    assert row.system_prompt == "sys"
    assert row.sampling["temperature"] == pytest.approx(0.2)
    assert row.sampling["top_p"] == pytest.approx(0.8)
    assert row.sampling["max_tokens"] == 1024


def test_legacy_mode_field_is_ignored(tmp_path: Path) -> None:
    """過去 prompt_bank.jsonl に残る `mode` 上書きフィールドは #94 で無視される。"""
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"prompt":"p","mode":"nothinking"}'])
    rows = load_prompt_bank(p)
    assert len(rows) == 1
    assert not hasattr(rows[0], "mode")


def test_blank_and_garbage_lines_skipped(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(
        p,
        [
            '{"prompt":"a"}',
            "",
            "   ",
            "not-json",
            '{"prompt":"b"}',
        ],
    )
    rows = load_prompt_bank(p)
    assert [r.prompt for r in rows] == ["a", "b"]


def test_missing_prompt_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"category":"x"}'])
    with pytest.raises(ValueError, match="prompt"):
        load_prompt_bank(p)


def test_merge_with_defaults_fills_missing_fields() -> None:
    cfg = Config()
    row = PromptRow(prompt="p", sampling={"temperature": 0.2})
    eff = merge_with_defaults(row, cfg)
    assert isinstance(eff, EffectiveSampling)
    assert eff.system_prompt.strip().startswith("あなたは丁寧")
    assert eff.sampling["temperature"] == pytest.approx(0.2)
    assert eff.sampling["top_p"] == pytest.approx(cfg.model.top_p)
    assert eff.sampling["top_k"] == cfg.model.top_k
    assert eff.sampling["max_tokens"] == cfg.model.num_predict
    assert eff.sampling["repetition_penalty"] == pytest.approx(cfg.model.repetition_penalty)


def test_merge_row_system_prompt_wins() -> None:
    cfg = Config()
    row = PromptRow(prompt="p", system_prompt="行内")
    eff = merge_with_defaults(row, cfg)
    assert eff.system_prompt == "行内"


def test_unicode_jsonl_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"prompt":"絵文字😀と日本語"}'])
    row = load_prompt_bank(p)[0]
    assert row.prompt == "絵文字😀と日本語"


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt_bank(tmp_path / "none.jsonl")


def test_merge_with_defaults_appends_tool_hint_when_tools_resolved() -> None:
    from joryu.tools import load_tools
    from joryu.variants import expand_variants

    cfg = Config()
    row = PromptRow(prompt="p", tool_ids=["search"])
    eff = merge_with_defaults(row, cfg, tools_registry=load_tools("tools.yaml"))
    assert len(eff.tools) == 1
    variant = expand_variants([row], cfg, tools_registry=load_tools("tools.yaml"))[0]
    assert "ツール" in variant.eff.system_prompt
    assert "架空" in variant.eff.system_prompt


def test_merge_with_defaults_uses_invocation_rules_in_hint() -> None:
    from joryu.prompt_bank import format_tool_usage_hint
    from joryu.tools import load_tools
    from joryu.variants import expand_variants

    cfg = Config()
    row = PromptRow(prompt="p", tool_ids=["search"])
    reg = load_tools("tools.yaml")
    eff = merge_with_defaults(row, cfg, tools_registry=reg)
    assert len(eff.tools) == 1
    variant = expand_variants([row], cfg, tools_registry=reg)[0]
    assert "利用可能なツール:" in variant.eff.system_prompt
    assert "- search:" in variant.eff.system_prompt
    assert reg["search"].invocation_rule in variant.eff.system_prompt
    hint = format_tool_usage_hint([reg["search"]])
    assert "事実・最新情報" in hint


def test_merge_with_defaults_legacy_hint_without_invocation_rules(tmp_path: Path) -> None:
    from joryu.tools import load_tools
    from joryu.variants import expand_variants

    p = tmp_path / "tools.yaml"
    p.write_text(
        "tools:\n  search:\n    description: d\n"
        "    parameters:\n      type: object\n      properties: {}\n",
        encoding="utf-8",
    )
    cfg = Config()
    row = PromptRow(prompt="p", tool_ids=["search"])
    reg = load_tools(p)
    eff = merge_with_defaults(row, cfg, tools_registry=reg)
    assert len(eff.tools) == 1
    variant = expand_variants([row], cfg, tools_registry=reg)[0]
    assert "利用可能なツールが提供されています。" in variant.eff.system_prompt
    assert "利用可能なツール:" not in variant.eff.system_prompt


def test_merge_with_defaults_no_tool_hint_without_tools() -> None:
    cfg = Config()
    row = PromptRow(prompt="p")
    eff = merge_with_defaults(row, cfg)
    assert "架空" not in eff.system_prompt


def test_merge_with_defaults_lowers_repetition_penalty_for_tools() -> None:
    from joryu.tools import load_tools

    cfg = Config()
    cfg.distill.tools_repetition_penalty = 1.0
    row = PromptRow(prompt="p", tool_ids=["search"])
    eff = merge_with_defaults(row, cfg, tools_registry=load_tools("tools.yaml"))
    assert eff.sampling["repetition_penalty"] == pytest.approx(1.0)


def test_merge_with_defaults_keeps_model_penalty_without_tools() -> None:
    cfg = Config()
    row = PromptRow(prompt="p")
    eff = merge_with_defaults(row, cfg)
    assert eff.sampling["repetition_penalty"] == pytest.approx(cfg.model.repetition_penalty)


def test_merge_row_repetition_penalty_overrides_tools_default() -> None:
    from joryu.tools import load_tools

    cfg = Config()
    row = PromptRow(prompt="p", tool_ids=["search"], sampling={"repetition_penalty": 1.2})
    eff = merge_with_defaults(row, cfg, tools_registry=load_tools("tools.yaml"))
    assert eff.sampling["repetition_penalty"] == pytest.approx(1.2)
    cfg = Config()
    row = PromptRow(prompt="p")
    eff = merge_with_defaults(row, cfg)
    assert "架空" not in eff.system_prompt
