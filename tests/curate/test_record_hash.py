"""record_hash の安定性テスト (R-21 scaffold)。"""

from __future__ import annotations

from joryu.curate.record_hash import compute_record_hash


def _base():
    return {
        "prompt": "p",
        "answer": "a",
        "mode": "nothinking",
        "sampling": {"temperature": 0.6, "top_p": 0.95},
        "system_prompt": "sys",
        "config_hash": "sha256-x",
    }


def test_record_hash_stable_across_calls():
    h1 = compute_record_hash(_base())
    h2 = compute_record_hash(_base())
    assert h1 == h2


def test_record_hash_invariant_to_sampling_order():
    a = _base()
    b = _base()
    b["sampling"] = {"top_p": 0.95, "temperature": 0.6}
    assert compute_record_hash(a) == compute_record_hash(b)


def test_record_hash_changes_with_answer():
    h1 = compute_record_hash(_base())
    rec = _base()
    rec["answer"] = "different"
    assert h1 != compute_record_hash(rec)


def test_record_hash_thinking_mode_includes_thinking():
    a = _base()
    a["mode"] = "thinking"
    a["thinking_trace"] = "trace-1"
    b = _base()
    b["mode"] = "thinking"
    b["thinking_trace"] = "trace-2"
    assert compute_record_hash(a) != compute_record_hash(b)
