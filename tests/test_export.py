"""export.py: zstd 圧縮 + SHA256 + meta.json + 任意の tar 束ね。"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
import zstandard as zstd

from joryu.export import ExportResult, export_jsonl


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_export_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "responses.jsonl"
    records = [
        {"prompt": "P1", "answer": "A1", "model": "M", "created_at": "2026-06-21T00:00:00+00:00"},
        {"prompt": "P2", "answer": "A2", "model": "M", "created_at": "2026-06-21T00:00:01+00:00"},
    ]
    _write_jsonl(src, records)

    out_dir = tmp_path / "exports"
    res = export_jsonl(src, out_dir=out_dir, level=3)

    assert isinstance(res, ExportResult)
    assert res.compressed_path.exists()
    assert res.compressed_path.suffix == ".zst"
    assert res.meta_path.exists()
    assert res.sha256sums_path.exists()
    assert res.tar_path is None

    # round-trip: decompress -> identical bytes (streaming)
    raw = src.read_bytes()
    dctx = zstd.ZstdDecompressor()
    with res.compressed_path.open("rb") as cf, io.BytesIO() as buf:
        dctx.copy_stream(cf, buf)
        restored = buf.getvalue()
    assert restored == raw


def test_meta_has_expected_fields(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    _write_jsonl(
        src,
        [
            {
                "prompt": "P1",
                "answer": "A1",
                "model": "Qwen3",
                "config_hash": "sha256-abc",
                "created_at": "2026-06-21T01:00:00+00:00",
            },
            {
                "prompt": "P2",
                "answer": "A2",
                "model": "Qwen3",
                "config_hash": "sha256-abc",
                "created_at": "2026-06-21T02:00:00+00:00",
            },
        ],
    )

    res = export_jsonl(src, out_dir=tmp_path / "out")
    meta = json.loads(res.meta_path.read_text(encoding="utf-8"))

    assert meta["records"] == 2
    assert meta["model"] == "Qwen3"
    assert meta["config_hash"] == "sha256-abc"
    assert meta["source_sha256"].startswith(("sha256-", ""))  # 形式に余裕を持たせる
    assert "compressed_sha256" in meta
    assert "compression" in meta and meta["compression"]["codec"] == "zstd"
    assert meta["compression"]["level"] >= 1
    assert meta["time_range"]["first"] == "2026-06-21T01:00:00+00:00"
    assert meta["time_range"]["last"] == "2026-06-21T02:00:00+00:00"
    assert "created_at" in meta
    assert meta["source_path"].endswith("r.jsonl")


def test_sha256sums_format(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    _write_jsonl(src, [{"prompt": "P", "answer": "A", "model": "M"}])
    res = export_jsonl(src, out_dir=tmp_path / "out")

    text = res.sha256sums_path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # 形式: "<hex>  <filename>"
    for ln in lines:
        parts = ln.split()
        assert len(parts) == 2
        assert len(parts[0]) == 64
    names = {ln.split()[1] for ln in lines}
    assert res.compressed_path.name in names
    assert res.meta_path.name in names


def test_bundle_tar(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    _write_jsonl(src, [{"prompt": "P", "answer": "A", "model": "M"}])
    res = export_jsonl(src, out_dir=tmp_path / "out", bundle_tar=True)

    assert res.tar_path is not None
    assert res.tar_path.exists()
    assert res.tar_path.suffix == ".tar"
    with tarfile.open(res.tar_path) as tf:
        names = set(tf.getnames())
    assert res.compressed_path.name in names
    assert res.meta_path.name in names
    assert res.sha256sums_path.name in names


def test_empty_jsonl_handled(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text("", encoding="utf-8")
    res = export_jsonl(src, out_dir=tmp_path / "out")
    meta = json.loads(res.meta_path.read_text(encoding="utf-8"))
    assert meta["records"] == 0
    assert meta["time_range"]["first"] is None
    assert meta["time_range"]["last"] is None


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_jsonl(tmp_path / "no.jsonl", out_dir=tmp_path / "out")


def test_compression_streaming_for_large_file(tmp_path: Path) -> None:
    """大きめの JSONL でもメモリにロードせず圧縮できる (Python 側はストリーミング)。"""
    src = tmp_path / "big.jsonl"
    with src.open("w", encoding="utf-8") as f:
        for i in range(5000):
            f.write(json.dumps({"prompt": f"P{i}", "answer": "X" * 200, "model": "M"}) + "\n")

    res = export_jsonl(src, out_dir=tmp_path / "out", level=3)
    # 圧縮された結果が元より小さい
    assert res.compressed_path.stat().st_size < src.stat().st_size

    # 解凍してレコード数が一致
    dctx = zstd.ZstdDecompressor()
    with res.compressed_path.open("rb") as cf, io.BytesIO() as buf:
        dctx.copy_stream(cf, buf)
        decoded = buf.getvalue().decode("utf-8")
    assert decoded.count("\n") == 5000
