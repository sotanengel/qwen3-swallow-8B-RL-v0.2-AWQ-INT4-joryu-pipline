"""counts module tests."""

from joryu.prompt_bank import PromptRow
from joryu.seed_gen.config import SeedGenConfig
from joryu.seed_gen.counts import count_by_domain, resolve_row_domain


def test_resolve_row_domain_from_category() -> None:
    cfg = SeedGenConfig.load("src/joryu/seed_gen/domains.yaml")
    row = PromptRow(prompt="p", category="数学・論理・抽象思考")
    assert resolve_row_domain(row, cfg) == "math"


def test_count_by_domain_mixed_rows() -> None:
    cfg = SeedGenConfig.load("src/joryu/seed_gen/domains.yaml")
    rows = [
        PromptRow(prompt="a", domain="coding"),
        PromptRow(prompt="b", category="数学・論理・抽象思考"),
    ]
    counts = count_by_domain(rows, cfg)
    assert counts["coding"] == 1
    assert counts["math"] == 1
