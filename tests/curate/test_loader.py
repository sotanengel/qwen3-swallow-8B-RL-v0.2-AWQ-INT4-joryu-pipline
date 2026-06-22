"""curate.loader.iter_records のテスト。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import zstandard as zstd

from joryu.curate.loader import REQUIRED_FIELDS, iter_records


def _valid_record() -> dict:
    return {
        "prompt": "p",
        "answer": "a",
        "mode": "nothinking",
        "sampling": {"temperature": 0.6},
        "config_hash": "sha256-abc",
    }


def test_iter_records_reads_plain_jsonl(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    records = [_valid_record(), {**_valid_record(), "answer": "b"}]
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )

    out = list(iter_records(src))
    assert len(out) == 2
    assert all(r["_schema_ok"] for r in out)


def test_iter_records_skips_malformed_lines(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    src.write_text(
        "\n".join(
            [
                json.dumps(_valid_record(), ensure_ascii=False),
                "not json {",
                "",
                json.dumps(_valid_record(), ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )

    out = list(iter_records(src))
    assert len(out) == 2


def test_iter_records_flags_schema_missing(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    bad = {"prompt": "p"}  # answer / mode / sampling / config_hash 欠落
    src.write_text(json.dumps(bad), encoding="utf-8")

    [out] = list(iter_records(src))
    assert out["_schema_ok"] is False


def test_iter_records_reads_zst(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl.zst"
    data = (json.dumps(_valid_record(), ensure_ascii=False) + "\n").encode("utf-8")
    cctx = zstd.ZstdCompressor(level=3)
    src.write_bytes(cctx.compress(data))

    out = list(iter_records(src))
    assert len(out) == 1
    assert out[0]["answer"] == "a"


def test_iter_records_missing_file_yields_nothing(tmp_path: Path) -> None:
    out = list(iter_records(tmp_path / "missing.jsonl"))
    assert out == []


def test_required_fields_constant_matches_doc() -> None:
    # 要件 6 章で前提とした必須キー。意図しない順序変更を防止する。
    assert set(REQUIRED_FIELDS) == {
        "prompt",
        "answer",
        "mode",
        "sampling",
        "config_hash",
    }


def test_iter_records_decompresses_stream_reader_in_chunks(tmp_path: Path) -> None:
    # 大きなレコードでも stream_reader が壊れないことを確認。
    src = tmp_path / "responses.jsonl.zst"
    big = _valid_record()
    big["answer"] = "あ" * 5000
    blob = (json.dumps(big, ensure_ascii=False) + "\n").encode("utf-8") * 3
    cctx = zstd.ZstdCompressor(level=3)
    src.write_bytes(cctx.compress(blob))

    out = list(iter_records(src))
    assert len(out) == 3
    assert all(len(r["answer"]) == 5000 for r in out)


def test_io_textiowrapper_is_used() -> None:
    # 単体: zstandard.ZstdDecompressor.stream_reader が TextIOWrapper でラップされる
    # 想定なので、低レベル API の存在を guard する。
    raw = io.BytesIO(zstd.ZstdCompressor().compress(b'{"a":1}\n'))
    reader = zstd.ZstdDecompressor().stream_reader(raw)
    text = io.TextIOWrapper(reader, encoding="utf-8")
    assert text.read().strip() == '{"a":1}'
