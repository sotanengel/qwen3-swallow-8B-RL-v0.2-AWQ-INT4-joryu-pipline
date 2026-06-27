"""SeedGenJobSpec 契約テスト。"""

from joryu.jobs.models import SeedGenJobSpec


def test_seed_gen_job_spec_to_argv() -> None:
    spec = SeedGenJobSpec(
        domain="math",
        target_total=100,
        fake_llm=True,
        dry_run=True,
        bank="data/bank.jsonl",
    )
    argv = spec.to_seed_gen_argv()
    assert "--domain" in argv
    assert "math" in argv
    assert "--fake-llm" in argv
    assert "--dry-run" in argv
    assert "--bank" in argv


def test_seed_gen_from_dict() -> None:
    spec = SeedGenJobSpec.from_dict({"target_total": 50, "resume": True})
    assert spec.target_total == 50
    assert spec.resume is True
