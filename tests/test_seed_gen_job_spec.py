"""SeedGenJobSpec 契約テスト。"""

import pytest

from joryu.jobs.models import (
    SEED_GEN_MODE_CHECK,
    SEED_GEN_MODE_CREATE,
    SeedGenJobSpec,
)


def test_seed_gen_job_spec_default_mode_is_create() -> None:
    spec = SeedGenJobSpec()
    assert spec.mode == SEED_GEN_MODE_CREATE


def test_seed_gen_job_spec_to_argv_create() -> None:
    spec = SeedGenJobSpec(
        domain="math",
        target_total=100,
        bank="data/bank.jsonl",
    )
    argv = spec.to_seed_gen_argv()
    assert "--mode" in argv
    assert argv[argv.index("--mode") + 1] == "create"
    assert "--domain" in argv
    assert "math" in argv
    assert "--bank" in argv
    assert "--fake-llm" not in argv
    assert "--dry-run" not in argv


def test_seed_gen_job_spec_to_argv_check() -> None:
    spec = SeedGenJobSpec(mode=SEED_GEN_MODE_CHECK, sim_threshold=0.9)
    argv = spec.to_seed_gen_argv()
    assert argv[argv.index("--mode") + 1] == "check"
    assert "--sim-threshold" in argv
    assert "0.9" in argv


def test_seed_gen_from_dict_roundtrip() -> None:
    spec = SeedGenJobSpec.from_dict({"target_total": 50, "resume": True, "mode": "check"})
    assert spec.target_total == 50
    assert spec.resume is True
    assert spec.mode == SEED_GEN_MODE_CHECK


def test_seed_gen_from_dict_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown seed_gen mode"):
        SeedGenJobSpec.from_dict({"mode": "bogus"})
