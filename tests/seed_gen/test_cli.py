"""seed-gen CLI tests."""

from pathlib import Path


def test_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    domains = Path("src/joryu/seed_gen/domains.yaml")
    if not domains.is_file():
        domains = Path(__file__).resolve().parents[2] / "src/joryu/seed_gen/domains.yaml"
    bank = tmp_path / "bank.jsonl"
    from joryu.seed_gen.cli import main

    rc = main(
        [
            "--domains-config",
            str(domains),
            "--bank",
            str(bank),
            "--dry-run",
            "--target-total",
            "100",
            "--domain",
            "math",
        ]
    )
    assert rc == 0
    assert not bank.exists()


def test_cli_fake_llm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    domains = Path(__file__).resolve().parents[2] / "src/joryu/seed_gen/domains.yaml"
    bank = tmp_path / "bank.jsonl"
    from joryu.seed_gen.cli import main

    rc = main(
        [
            "--domains-config",
            str(domains),
            "--bank",
            str(bank),
            "--fake-llm",
            "--target-total",
            "20",
            "--domain",
            "general_qa",
            "--batch-size",
            "4",
        ]
    )
    assert rc == 0
    assert bank.is_file()
