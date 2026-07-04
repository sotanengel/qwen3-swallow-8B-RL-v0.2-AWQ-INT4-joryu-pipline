"""prompt check state (checked_keys) tests."""

from __future__ import annotations

import json
from pathlib import Path

from joryu.core.prompt_bank import PromptRow
from joryu.seed_gen.check_state import (
    compute_check_status,
    mark_checked,
    partition_by_checked,
    prompt_check_key,
)
from joryu.seed_gen.writer import SeedGenState, load_state, save_state


def test_prompt_check_key_uses_id_when_present() -> None:
    row = PromptRow.model_validate({"id": "abc-123", "prompt": "hello"})
    assert prompt_check_key(row) == "id:abc-123"


def test_prompt_check_key_uses_hash_when_id_missing() -> None:
    row = PromptRow.model_validate({"prompt": "legacy prompt"})
    key = prompt_check_key(row)
    assert key.startswith("hash:")
    assert len(key) > len("hash:")


def test_partition_by_checked_splits_rows() -> None:
    rows = [
        PromptRow.model_validate({"id": "a", "prompt": "one"}),
        PromptRow.model_validate({"id": "b", "prompt": "two"}),
        PromptRow.model_validate({"prompt": "legacy"}),
    ]
    checked, unchecked = partition_by_checked(rows, {"id:a", prompt_check_key(rows[2])})
    assert [r.id for r in checked if r.id] == ["a"]
    assert len(checked) == 2
    assert len(unchecked) == 1
    assert unchecked[0].id == "b"


def test_mark_checked_adds_keys_and_persists_in_state_json(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    rows = [
        PromptRow.model_validate({"id": "x1", "prompt": "p1", "domain": "math"}),
        PromptRow.model_validate({"id": "x2", "prompt": "p2", "domain": "math"}),
    ]
    state = load_state(state_path)
    mark_checked(state, [prompt_check_key(rows[0])])
    save_state(state_path, state)

    reloaded = load_state(state_path)
    assert prompt_check_key(rows[0]) in reloaded.prompt_check.checked_keys
    assert prompt_check_key(rows[1]) not in reloaded.prompt_check.checked_keys

    status = compute_check_status(rows, reloaded.prompt_check.checked_keys)
    assert status.bank_total == 2
    assert status.checked_count == 1
    assert status.unchecked_count == 1
    assert status.check_completed is False


def test_compute_check_status_completed_when_all_checked() -> None:
    rows = [PromptRow.model_validate({"id": "only", "prompt": "solo"})]
    key = prompt_check_key(rows[0])
    status = compute_check_status(rows, {key})
    assert status.check_completed is True
    assert status.unchecked_count == 0


def test_load_state_backward_compat_without_prompt_check(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"updated_at": "2026-01-01T00:00:00+00:00", "domains": {}}) + "\n",
        encoding="utf-8",
    )
    state = load_state(state_path)
    assert state.prompt_check.checked_keys == set()


def test_mark_all_unchecked_by_domain(tmp_path: Path) -> None:
    rows = [
        PromptRow.model_validate({"id": "m1", "prompt": "a", "domain": "math"}),
        PromptRow.model_validate({"id": "m2", "prompt": "b", "domain": "math"}),
        PromptRow.model_validate({"id": "g1", "prompt": "c", "domain": "general_qa"}),
    ]
    state = SeedGenState()
    mark_checked(state, [prompt_check_key(r) for r in rows if r.domain == "math"])
    assert prompt_check_key(rows[0]) in state.prompt_check.checked_keys
    assert prompt_check_key(rows[1]) in state.prompt_check.checked_keys
    assert prompt_check_key(rows[2]) not in state.prompt_check.checked_keys
