"""差分実行キャッシュテスト (R-20 / R-23)。"""

from __future__ import annotations

from pathlib import Path

from joryu.curate.cache import (
    CacheCounters,
    CachedRecord,
    auto_detect_cache_paths,
    load_cache_index,
    signal_result_from_cache,
)
from tests.helpers.jsonl import write_jsonl


def _write_scores(p: Path, rows: list[dict]) -> None:
    write_jsonl(p, rows)


def _row(rh: str, scores: dict[str, float], versions: dict[str, str], rejected_by=None):
    return {
        "record_hash": rh,
        "signal_scores": scores,
        "signal_versions": versions,
        "signal_raw": {},
        "final_score": sum(scores.values()) / len(scores) if scores else 0.0,
        "accepted": not (rejected_by or []),
        "rejected_by": rejected_by or [],
    }


def test_load_cache_index_missing_path_is_skipped(tmp_path: Path) -> None:
    index = load_cache_index([tmp_path / "no.jsonl"])
    assert len(index) == 0
    assert index.sources == []


def test_load_cache_index_collects_records(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(p, [_row("h1", {"LEN-A": 0.9}, {"LEN-A": "v1"})])
    index = load_cache_index([p])
    assert len(index) == 1
    assert "h1" in index.records


def test_load_cache_index_accepts_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_1"
    _write_scores(run_dir / "scores.jsonl", [_row("h1", {}, {})])
    index = load_cache_index([run_dir])
    assert len(index) == 1


def test_load_cache_index_later_paths_override(tmp_path: Path) -> None:
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    _write_scores(p1, [_row("h1", {"LEN-A": 0.5}, {"LEN-A": "v1"})])
    _write_scores(p2, [_row("h1", {"LEN-A": 0.9}, {"LEN-A": "v1"})])
    index = load_cache_index([p1, p2])
    assert index.records["h1"].signal_scores["LEN-A"] == 0.9


def test_lookup_returns_full_hit_when_all_versions_match(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(
        p,
        [
            _row(
                "h1",
                {"LEN-A": 1.0, "LLM-RUBRIC": 0.8},
                {"LEN-A": "v1", "LLM-RUBRIC": "v1"},
            )
        ],
    )
    index = load_cache_index([p])
    reuse = index.lookup("h1", expected_versions={"LEN-A": "v1", "LLM-RUBRIC": "v1"})
    assert reuse.is_full_hit
    assert reuse.is_partial_hit is False
    assert reuse.is_new_record is False
    assert reuse.reusable_signals == {"LEN-A", "LLM-RUBRIC"}
    assert reuse.stale_signals == set()


def test_lookup_returns_partial_hit_when_one_version_stale(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(
        p,
        [
            _row(
                "h1",
                {"LEN-A": 1.0, "LLM-RUBRIC": 0.8},
                {"LEN-A": "v1", "LLM-RUBRIC": "v1"},
            )
        ],
    )
    index = load_cache_index([p])
    reuse = index.lookup("h1", expected_versions={"LEN-A": "v1", "LLM-RUBRIC": "v2"})
    assert reuse.is_partial_hit
    assert reuse.is_full_hit is False
    assert reuse.reusable_signals == {"LEN-A"}
    assert reuse.stale_signals == {"LLM-RUBRIC"}


def test_lookup_returns_new_when_hash_missing(tmp_path: Path) -> None:
    p = tmp_path / "scores.jsonl"
    _write_scores(p, [_row("h1", {}, {})])
    index = load_cache_index([p])
    reuse = index.lookup("missing", expected_versions={"LEN-A": "v1"})
    assert reuse.is_new_record is True
    assert reuse.cached is None


def test_signal_result_from_cache_carries_hard_reject_flag() -> None:
    cached = CachedRecord(
        record_hash="h1",
        signal_scores={"LEN-A": 0.0, "LANG-JA": 0.8},
        signal_versions={"LEN-A": "v1", "LANG-JA": "v1"},
        rejected_by=["LEN-A"],
    )
    r1 = signal_result_from_cache("LEN-A", "v1", cached)
    r2 = signal_result_from_cache("LANG-JA", "v1", cached)
    assert r1.hard_reject is True
    assert r2.hard_reject is False
    assert r1.score == 0.0
    assert r2.score == 0.8


def test_auto_detect_cache_paths_picks_newest(tmp_path: Path) -> None:
    root = tmp_path
    older = root / "run_a"
    newer = root / "run_b"
    _write_scores(older / "scores.jsonl", [_row("h1", {}, {})])
    _write_scores(newer / "scores.jsonl", [_row("h2", {}, {})])
    # 強制的に mtime を後ろにする
    import os
    import time

    os.utime(older / "scores.jsonl", (time.time() - 100, time.time() - 100))
    paths = auto_detect_cache_paths(root, current_dst=root / "run_c")
    assert paths == [newer / "scores.jsonl"]


def test_auto_detect_cache_paths_excludes_current_dst(tmp_path: Path) -> None:
    root = tmp_path
    current = root / "current"
    _write_scores(current / "scores.jsonl", [_row("h1", {}, {})])
    paths = auto_detect_cache_paths(root, current_dst=current)
    assert paths == []


def test_cache_counters_default() -> None:
    c = CacheCounters()
    assert c.cache_hits_full == 0
    assert c.cache_hits_partial == 0
    assert c.newly_evaluated == 0
    assert c.llm_calls_saved == 0
