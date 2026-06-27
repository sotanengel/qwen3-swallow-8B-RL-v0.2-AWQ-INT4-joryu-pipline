"""Fake LLM pipeline E2E."""

from pathlib import Path

from joryu.seed_gen.config import SeedGenConfig
from joryu.seed_gen.pipeline import PipelineOptions, run_pipeline


def test_pipeline_fake_single_domain(tmp_path: Path) -> None:
    domains = tmp_path / "domains.yaml"
    domains.write_text(
        """
version: 1
target_total: 100
legacy_category_aliases: {}
domains:
  - key: general_qa
    target: 100
    seed_templates: ["{theme}"]
    themes: ["test"]
""".strip(),
        encoding="utf-8",
    )
    bank = tmp_path / "bank.jsonl"
    state = tmp_path / "state.json"
    cfg = SeedGenConfig.load(domains).with_target_total(20)
    opts = PipelineOptions(
        bank_path=bank,
        state_path=state,
        config=cfg.filter_domain("general_qa"),
        fake_llm=True,
        batch_size=4,
        target_total_override=20,
    )
    rc = run_pipeline(opts)
    assert rc == 0
    lines = bank.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
