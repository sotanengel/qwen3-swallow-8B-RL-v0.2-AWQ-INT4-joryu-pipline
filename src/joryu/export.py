"""JSONL を zstd 圧縮しメタデータ・SHA256・任意の tar 束ねで出力する。"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import zstandard as zstd

from joryu.io.jsonl import iter_jsonl

DEFAULT_LEVEL = 19


@dataclass
class ExportResult:
    """`export_jsonl` の戻り値。生成された各ファイルのパス。"""

    out_dir: Path
    compressed_path: Path
    meta_path: Path
    sha256sums_path: Path
    tar_path: Path | None


def _hash_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _stream_compress(src: Path, dst: Path, level: int) -> None:
    cctx = zstd.ZstdCompressor(level=level)
    with src.open("rb") as fin, dst.open("wb") as fout:
        cctx.copy_stream(fin, fout)


def _scan_jsonl(src: Path) -> dict:
    """JSONL を 1 パスで走査して `meta.json` 用の集計値を作る。"""
    records = 0
    model: str | None = None
    config_hash: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None

    for rec in iter_jsonl(src):
        records += 1
        if model is None:
            m = rec.get("model")
            if isinstance(m, str):
                model = m
        if config_hash is None:
            c = rec.get("config_hash")
            if isinstance(c, str):
                config_hash = c
        ts = rec.get("created_at")
        if isinstance(ts, str) and ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

    return {
        "records": records,
        "model": model,
        "config_hash": config_hash,
        "time_range": {"first": first_ts, "last": last_ts},
    }


def export_jsonl(
    source: str | Path,
    *,
    out_dir: str | Path,
    level: int = DEFAULT_LEVEL,
    bundle_tar: bool = False,
    timestamp: str | None = None,
) -> ExportResult:
    """JSONL を `<out_dir>/<timestamp>/` に zstd 圧縮 + meta + SHA256SUMS で出力する。

    Parameters
    ----------
    source:
        圧縮対象 JSONL。
    out_dir:
        親出力ディレクトリ。タイムスタンプ付サブディレクトリが自動作成される。
    level:
        zstd 圧縮レベル (1-22)。
    bundle_tar:
        True なら同階層に ``<timestamp>.tar`` を作成し、3 ファイルを束ねる。
    timestamp:
        サブディレクトリ名 (未指定なら ``YYYYMMDDTHHMMSSZ``)。
    """
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"export source not found: {src}")

    parent = Path(out_dir)
    ts = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sub = parent / ts
    sub.mkdir(parents=True, exist_ok=True)

    compressed = sub / "responses.jsonl.zst"
    meta_path = sub / "meta.json"
    sums_path = sub / "SHA256SUMS"

    _stream_compress(src, compressed, level=level)

    source_sha256 = _hash_file(src)
    compressed_sha256 = _hash_file(compressed)

    summary = _scan_jsonl(src)
    meta = {
        "records": summary["records"],
        "model": summary["model"],
        "config_hash": summary["config_hash"],
        "time_range": summary["time_range"],
        "source_path": str(src),
        "source_sha256": source_sha256,
        "source_bytes": src.stat().st_size,
        "compressed_path": compressed.name,
        "compressed_sha256": compressed_sha256,
        "compressed_bytes": compressed.stat().st_size,
        "compression": {"codec": "zstd", "level": level},
        "created_at": datetime.now(UTC).isoformat(),
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # SHA256SUMS は compressed + meta を対象 (sha256sum -c 互換)。
    sums_lines = [
        f"{compressed_sha256}  {compressed.name}",
        f"{_hash_file(meta_path)}  {meta_path.name}",
    ]
    sums_path.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    tar_path: Path | None = None
    if bundle_tar:
        tar_path = parent / f"{ts}.tar"
        with tarfile.open(tar_path, "w") as tf:
            for p in (compressed, meta_path, sums_path):
                tf.add(p, arcname=p.name)

    return ExportResult(
        out_dir=sub,
        compressed_path=compressed,
        meta_path=meta_path,
        sha256sums_path=sums_path,
        tar_path=tar_path,
    )


def decompress_to_bytes(path: str | Path) -> bytes:
    """テスト・ユーティリティ用: zstd ファイルを bytes に展開する。"""
    dctx = zstd.ZstdDecompressor()
    with Path(path).open("rb") as f, io.BytesIO() as buf:
        dctx.copy_stream(f, buf)
        return buf.getvalue()
