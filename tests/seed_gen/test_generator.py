"""generator parse tests."""

import pytest

from joryu.seed_gen.config import DomainSpec
from joryu.seed_gen.generator import (
    FakeSeedGenerator,
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


def test_fake_generator_batch() -> None:
    gen = FakeSeedGenerator()
    domain = DomainSpec(key="math", target=10, seed_templates=[], themes=[])
    out = gen.generate_batch(domain=domain, n=3, sampling=gen.next_sampling())
    assert len(out) == 3
    assert all("[fake:math:" in p for p in out)


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


def test_openai_generator_forbidden_model() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        OpenAICompatibleSeedGenerator(base_url="http://x", model="Qwen3-Swallow-test")
