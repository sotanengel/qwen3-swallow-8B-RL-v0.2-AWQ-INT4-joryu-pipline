"""seed_gen config loader tests."""

from pathlib import Path

import pytest

from joryu.seed_gen.config import SeedGenConfig


@pytest.fixture
def domains_path() -> Path:
    return Path("src/joryu/seed_gen/domains.yaml")


def test_load_fifteen_domains(domains_path: Path) -> None:
    cfg = SeedGenConfig.load(domains_path)
    assert len(cfg.domains) == 15
    assert cfg.target_total == 230000
    assert sum(d.target for d in cfg.domains) == cfg.target_total


def test_with_target_total_scales(domains_path: Path) -> None:
    cfg = SeedGenConfig.load(domains_path).with_target_total(1000)
    assert cfg.target_total == 1000
    math = next(d for d in cfg.domains if d.key == "math")
    assert math.target == pytest.approx(122, abs=2)


def test_filter_domain(domains_path: Path) -> None:
    cfg = SeedGenConfig.load(domains_path).filter_domain("math")
    assert len(cfg.domains) == 1
    assert cfg.domains[0].key == "math"


def test_filter_domain_unknown(domains_path: Path) -> None:
    cfg = SeedGenConfig.load(domains_path)
    with pytest.raises(ValueError, match="unknown domain"):
        cfg.filter_domain("not_a_domain")


def test_category_aliases_map(domains_path: Path) -> None:
    cfg = SeedGenConfig.load(domains_path)
    mapping = cfg.category_to_domain_map()
    assert mapping["数学・論理・抽象思考"] == "math"
