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
    assert row.mode is None
    assert row.sampling == {}
    assert row.system_prompt is None


def test_full_row_carries_overrides(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(
        p,
        [
            (
                '{"prompt":"p","category":"国語","style_id":"essay",'
                '"mode":"nothinking","system_prompt":"sys",'
                '"sampling":{"temperature":0.2,"top_p":0.8,"max_tokens":1024}}'
            )
        ],
    )
    row = load_prompt_bank(p)[0]
    assert row.category == "国語"
    assert row.style_id == "essay"
    assert row.mode == "nothinking"
    assert row.system_prompt == "sys"
    assert row.sampling["temperature"] == pytest.approx(0.2)
    assert row.sampling["top_p"] == pytest.approx(0.8)
    assert row.sampling["max_tokens"] == 1024


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


def test_unknown_mode_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"prompt":"p","mode":"random"}'])
    with pytest.raises(ValueError, match="mode"):
        load_prompt_bank(p)


def test_merge_with_defaults_fills_missing_fields() -> None:
    cfg = Config()
    row = PromptRow(prompt="p", sampling={"temperature": 0.2})
    eff = merge_with_defaults(row, cfg)
    assert isinstance(eff, EffectiveSampling)
    assert eff.mode == cfg.model.mode
    assert eff.system_prompt.strip().startswith("あなたは丁寧")
    assert eff.sampling["temperature"] == pytest.approx(0.2)
    assert eff.sampling["top_p"] == pytest.approx(cfg.model.top_p)
    assert eff.sampling["top_k"] == cfg.model.top_k
    assert eff.sampling["max_tokens"] == cfg.model.num_predict
    assert eff.sampling["repetition_penalty"] == pytest.approx(cfg.model.repetition_penalty)


def test_merge_row_mode_wins() -> None:
    cfg = Config()
    cfg.model.mode = "thinking"
    row = PromptRow(prompt="p", mode="nothinking", system_prompt="行内")
    eff = merge_with_defaults(row, cfg)
    assert eff.mode == "nothinking"
    assert eff.system_prompt == "行内"


def test_unicode_jsonl_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(p, ['{"prompt":"絵文字😀と日本語"}'])
    row = load_prompt_bank(p)[0]
    assert row.prompt == "絵文字😀と日本語"


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt_bank(tmp_path / "none.jsonl")
