"""curate/purge.py: 棄却レコードの蒸留元削除テスト (R-26)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.curate.loader import normalize_record
from joryu.curate.purge import purge_rejected_from_source
from joryu.curate.record_hash import compute_record_hash
from joryu.persistence.progress import load_done_keys
from joryu.persistence.responses_store import load_records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


KEEP_RECORD = {
    "prompt": "桜の特徴を3行で",
    "answer": (
        "桜は春に咲く日本の代表的な花で、薄いピンク色の花弁が特徴です。"
        "開花は地域によって異なり、北上していく様子は桜前線と呼ばれます。"
        "短い期間で散る儚さが古来から多くの和歌に詠まれてきました。"
    ),
    "mode": "nothinking",
    "sampling": {"temperature": 0.6, "top_p": 0.95},
    "system_prompt": "あなたは日本語アシスタントです。",
    "config_hash": "sha256-test",
    "style_id": "prose",
    "category": "国語",
}

REJECT_RECORD = {
    "prompt": "短い質問",
    "answer": "短",
    "mode": "nothinking",
    "sampling": {"temperature": 0.6, "top_p": 0.95},
    "system_prompt": "",
    "config_hash": "sha256-test",
    "style_id": "prose",
    "category": "国語",
}


def test_purge_removes_rejected_records_from_source(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    rejected_path = tmp_path / "responses.rejected.jsonl"
    _write_jsonl(src, [KEEP_RECORD, REJECT_RECORD])
    rejected_out = dict(REJECT_RECORD)
    rejected_out["rejected_by"] = ["LEN-A"]
    rejected_out["final_score"] = 0.0
    _write_jsonl(rejected_path, [rejected_out])

    result = purge_rejected_from_source(src, rejected_path)

    assert result.purged == 1
    assert result.not_found == 0
    assert result.src_before == 2
    assert result.src_after == 1
    remaining = load_records(src)
    assert len(remaining) == 1
    assert remaining[0]["prompt"] == KEEP_RECORD["prompt"]


def test_purge_empty_rejected_leaves_source_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    rejected_path = tmp_path / "responses.rejected.jsonl"
    _write_jsonl(src, [KEEP_RECORD])
    rejected_path.write_text("", encoding="utf-8")

    result = purge_rejected_from_source(src, rejected_path)

    assert result.purged == 0
    assert result.not_found == 0
    assert result.src_before == 1
    assert result.src_after == 1
    assert load_records(src) == [KEEP_RECORD]


def test_purge_counts_not_found_when_rejected_missing_from_source(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    rejected_path = tmp_path / "responses.rejected.jsonl"
    _write_jsonl(src, [KEEP_RECORD])
    rejected_out = dict(REJECT_RECORD)
    rejected_out["rejected_by"] = ["LEN-A"]
    _write_jsonl(rejected_path, [rejected_out])

    result = purge_rejected_from_source(src, rejected_path)

    assert result.purged == 0
    assert result.not_found == 1
    assert result.src_after == 1


def test_purge_frees_run_key_for_redistill(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    rejected_path = tmp_path / "responses.rejected.jsonl"
    _write_jsonl(src, [REJECT_RECORD])
    rejected_out = dict(REJECT_RECORD)
    rejected_out["rejected_by"] = ["LEN-A"]
    _write_jsonl(rejected_path, [rejected_out])

    assert load_done_keys(src)
    purge_rejected_from_source(src, rejected_path)
    assert not load_done_keys(src)


def test_purge_uses_record_hash_not_prompt_only(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    rejected_path = tmp_path / "responses.rejected.jsonl"
    other = dict(REJECT_RECORD)
    other["answer"] = "別の回答です。十分な長さのテキストを含みます。" * 3
    _write_jsonl(src, [REJECT_RECORD, other])
    rejected_out = dict(REJECT_RECORD)
    rejected_out["rejected_by"] = ["LEN-A"]
    _write_jsonl(rejected_path, [rejected_out])

    result = purge_rejected_from_source(src, rejected_path)

    assert result.purged == 1
    remaining = load_records(src)
    assert len(remaining) == 1
    assert compute_record_hash(remaining[0]) == compute_record_hash(other)


def test_purge_matches_distill_records_without_mode_field(tmp_path: Path) -> None:
    """#94 蒸留 JSONL (mode 省略) でも curate と同一 hash で削除できる。"""
    reject_src = {
        "prompt": "短い質問",
        "answer": "短",
        "sampling": {"temperature": 0.6, "top_p": 0.95},
        "config_hash": "sha256-test",
        "thinking_trace": "思考トレース",
        "system_prompt": "",
        "style_id": "prose",
    }
    keep_src = {
        **reject_src,
        "answer": "十分な長さの回答です。" * 4,
    }
    src = tmp_path / "responses.jsonl"
    _write_jsonl(src, [keep_src, reject_src])

    rejected_out = dict(reject_src)
    normalize_record(rejected_out)
    rejected_out["rejected_by"] = ["LEN-A"]
    rejected_path = tmp_path / "responses.rejected.jsonl"
    _write_jsonl(rejected_path, [rejected_out])

    result = purge_rejected_from_source(src, rejected_path)

    assert result.purged == 1
    assert result.not_found == 0
    assert len(load_records(src)) == 1


def test_purge_prefers_scores_record_hash(tmp_path: Path) -> None:
    """scores.jsonl の record_hash を優先して照合する。"""
    reject_src = {
        "prompt": "短い質問",
        "answer": "短",
        "sampling": {"temperature": 0.6, "top_p": 0.95},
        "config_hash": "sha256-test",
        "thinking_trace": "思考トレース",
        "system_prompt": "",
    }
    keep_src = {
        **reject_src,
        "answer": "十分な長さの回答です。" * 4,
    }
    src = tmp_path / "responses.jsonl"
    _write_jsonl(src, [keep_src, reject_src])

    normalized = dict(reject_src)
    normalize_record(normalized)
    record_hash = compute_record_hash(normalized)
    scores_path = tmp_path / "scores.jsonl"
    scores_path.write_text(
        json.dumps(
            {
                "record_hash": record_hash,
                "accepted": False,
                "rejected_by": ["LEN-A"],
                "final_score": 0.0,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = purge_rejected_from_source(
        src,
        tmp_path / "missing-rejected.jsonl",
        scores_path=scores_path,
    )

    assert result.purged == 1
    assert len(load_records(src)) == 1
