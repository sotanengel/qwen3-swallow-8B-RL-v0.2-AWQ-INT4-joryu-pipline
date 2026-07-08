from __future__ import annotations

from pathlib import Path

from joryu.bench.prompts import read_prompt_bank_jsonl, write_default_prompt_bank_jsonl


def test_default_prompt_bank_matches_fixture(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    fixture = repo / "tests" / "fixtures" / "bench" / "prompts.jsonl"
    out = tmp_path / "prompts.jsonl"

    write_default_prompt_bank_jsonl(out)

    assert read_prompt_bank_jsonl(out) == read_prompt_bank_jsonl(fixture)
