"""generator parse tests."""

import httpx
import pytest
import respx

from joryu.seed_gen.config import DomainSpec
from joryu.seed_gen.generator import (
    OpenAICompatibleSeedGenerator,
    SamplingParams,
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


def _make_domain() -> DomainSpec:
    return DomainSpec(
        key="general_qa",
        target=1,
        seed_templates=["{theme}"],
        themes=["テーマ"],
    )


@respx.mock
def test_openai_generator_generate_batch_ok() -> None:
    gen = OpenAICompatibleSeedGenerator(
        base_url="http://mock/v1",
        model="Qwen/Qwen2.5-7B-Instruct-AWQ",
        api_key="secret",
    )
    respx.post("http://mock/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '["A", "B"]'}}]},
        )
    )
    out = gen.generate_batch(domain=_make_domain(), n=2, sampling=gen.next_sampling())
    assert out == ["A", "B"]


@respx.mock
def test_openai_generator_generate_batch_bad_shape_returns_empty() -> None:
    gen = OpenAICompatibleSeedGenerator(
        base_url="http://mock/v1",
        model="Qwen/Qwen2.5-7B-Instruct-AWQ",
    )
    respx.post("http://mock/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    out = gen.generate_batch(
        domain=_make_domain(), n=1, sampling=SamplingParams(temperature=0.7, top_p=0.9)
    )
    assert out == []


@respx.mock
def test_openai_generator_generate_batch_http_error_returns_empty() -> None:
    gen = OpenAICompatibleSeedGenerator(
        base_url="http://mock/v1",
        model="Qwen/Qwen2.5-7B-Instruct-AWQ",
    )
    respx.post("http://mock/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="boom")
    )
    out = gen.generate_batch(
        domain=_make_domain(), n=1, sampling=SamplingParams(temperature=0.7, top_p=0.9)
    )
    assert out == []


def test_openai_generator_next_sampling_rotates() -> None:
    gen = OpenAICompatibleSeedGenerator(
        base_url="http://mock/v1",
        model="Qwen/Qwen2.5-7B-Instruct-AWQ",
    )
    s1 = gen.next_sampling()
    s2 = gen.next_sampling()
    assert s1 != s2 or s1.temperature != s2.temperature or s1.top_p != s2.top_p
