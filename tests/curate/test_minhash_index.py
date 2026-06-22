"""MinHash 永続化テスト (R-24)。"""

from __future__ import annotations

from pathlib import Path

from joryu.curate.minhash_index import (
    DEFAULT_INDEX_FILENAME,
    GlobalDuplicateIndex,
)


def test_first_insert_is_not_duplicate() -> None:
    idx = GlobalDuplicateIndex()
    is_dup, _ = idx.query_and_insert("h1", "今日は良い天気ですね。")
    assert is_dup is False
    assert len(idx) == 1


def test_exact_duplicate_detected() -> None:
    idx = GlobalDuplicateIndex()
    idx.query_and_insert("h1", "今日は良い天気ですね。")
    is_dup, dup_with = idx.query_and_insert("h2", "今日は良い天気ですね。")
    assert is_dup is True
    assert dup_with is not None


def test_distinct_text_not_duplicate() -> None:
    idx = GlobalDuplicateIndex()
    idx.query_and_insert("h1", "今日は良い天気ですね。")
    is_dup, _ = idx.query_and_insert("h2", "明日は雨が降る予報です。")
    assert is_dup is False


def test_empty_text_not_duplicate() -> None:
    idx = GlobalDuplicateIndex()
    is_dup, _ = idx.query_and_insert("h1", "")
    assert is_dup is False
    assert len(idx) == 0


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    idx = GlobalDuplicateIndex()
    idx.query_and_insert("h1", "今日は良い天気ですね。")
    idx.query_and_insert("h2", "明日は雨が降る予報です。")
    p = tmp_path / DEFAULT_INDEX_FILENAME
    idx.save(p)
    assert p.exists()

    loaded = GlobalDuplicateIndex.load(p)
    assert len(loaded) == 2
    # 既知レコードの再投入は重複扱い
    is_dup, _ = loaded.query_and_insert("h1_again", "今日は良い天気ですね。")
    assert is_dup is True


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    idx = GlobalDuplicateIndex.load(tmp_path / "missing.index")
    assert len(idx) == 0


def test_load_corrupted_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / DEFAULT_INDEX_FILENAME
    p.write_bytes(b"not a real pickle")
    idx = GlobalDuplicateIndex.load(p)
    assert len(idx) == 0


def test_incremental_cross_run(tmp_path: Path) -> None:
    """ラン 1 で 1 件 insert → 保存 → ラン 2 でロードして同テキストを query すると重複判定。"""
    p = tmp_path / DEFAULT_INDEX_FILENAME
    run1 = GlobalDuplicateIndex()
    run1.query_and_insert("h1", "プロンプト1への回答です。")
    run1.save(p)

    run2 = GlobalDuplicateIndex.load(p)
    is_dup, _ = run2.query_and_insert("h2", "プロンプト1への回答です。")
    assert is_dup is True


def test_backend_is_either_minhash_or_sha1() -> None:
    idx = GlobalDuplicateIndex()
    assert idx.backend in ("minhash", "sha1")
