"""generator parse tests."""

import pytest

from joryu.seed_gen.config import DomainSpec
from joryu.seed_gen.generator import (
    OpenAICompatibleSeedGenerator,
    build_seed_prompt,
    build_user_message,
    parse_prompt_array,
)


def test_parse_prompt_array_ok() -> None:
    text = '["プロンプトA", "プロンプトB"]'
    assert parse_prompt_array(text) == ["プロンプトA", "プロンプトB"]


def test_parse_prompt_array_invalid_returns_empty() -> None:
    assert parse_prompt_array("not json") == []


def test_parse_prompt_array_non_string_items_skipped() -> None:
    assert parse_prompt_array('["ok", 1, ""]') == ["ok"]


def test_parse_prompt_array_multiple_arrays() -> None:
    """LLM が改行区切りの複数配列を返しても全部拾う。"""
    text = '["A"]\n["B", "C"]\n["D"]'
    assert parse_prompt_array(text) == ["A", "B", "C", "D"]


def test_parse_prompt_array_doubled_quotes() -> None:
    """`[""foo""]` のような二重 quote は正規化して復元する。"""
    text = '[""データを抽出""]\n[""在庫を集計""]'
    assert parse_prompt_array(text) == ["データを抽出", "在庫を集計"]


def test_parse_prompt_array_fallback_quoted_strings() -> None:
    """配列が全滅した場合は quote された文字列だけでも拾う。"""
    text = 'ここには JSON がありません。 "拾えるプロンプト" と "もうひとつ"'
    assert parse_prompt_array(text) == ["拾えるプロンプト", "もうひとつ"]


def test_build_seed_prompt_and_user_message() -> None:
    domain = DomainSpec(
        key="math",
        target=1,
        seed_templates=["{theme}を説明"],
        themes=["代数"],
    )
    import random

    rng = random.Random(0)
    seed = build_seed_prompt(domain, rng)
    assert "代数" in seed
    msg = build_user_message(domain, 2, seed)
    assert "math" in msg
    assert "2" in msg
    assert "JSON 配列" in msg


def test_openai_generator_forbidden_model() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        OpenAICompatibleSeedGenerator(base_url="http://x", model="Qwen3-Swallow-test")
