"""writer atomic append tests."""

from pathlib import Path

from joryu.seed_gen.writer import (
    SeedGenState,
    atomic_append_jsonl,
    count_bank_rows,
    load_state,
    make_seed_row,
    read_bank_bytes,
    save_state,
)


def test_atomic_append_preserves_existing_bytes(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    bank.write_text('{"prompt":"legacy","category":"社会・現代問題"}\n', encoding="utf-8")
    before = read_bank_bytes(bank)
    atomic_append_jsonl(bank, [make_seed_row("new prompt", "general_qa")])
    after = read_bank_bytes(bank)
    assert after.startswith(before)
    assert b"general_qa" in after


def test_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = SeedGenState()
    save_state(path, state)
    loaded = load_state(path)
    assert loaded.updated_at


def test_count_bank_rows(tmp_path: Path) -> None:
    bank = tmp_path / "b.jsonl"
    bank.write_text('{"prompt":"a"}\n{"prompt":"b"}\n', encoding="utf-8")
    assert count_bank_rows(bank) == 2
