"""curation_meta.json 出力 (R-17 / R-25)。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def compute_file_sha256(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256-" + h.hexdigest()


def write_curation_meta(
    dst_dir: str | Path,
    *,
    src_path: str | Path,
    input_records: int,
    kept: int,
    rejected: int,
    curate_fingerprints: dict[str, str],
    judge_model: str,
    judge_mode: str,
    signal_versions: dict[str, str],
    cli_args: dict[str, Any],
    git_sha: str | None = None,
    llm_calls_total: int = 0,
) -> Path:
    """`curation_meta.json` を書き出してそのパスを返す。"""
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    out = dst / "curation_meta.json"
    payload: dict[str, Any] = {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "source": {
            "path": str(src_path),
            "sha256": compute_file_sha256(src_path),
            "input_records": input_records,
        },
        "summary": {
            "kept": kept,
            "rejected": rejected,
            "keep_rate": (kept / input_records) if input_records else 0.0,
        },
        "curate_config": {
            "fingerprints": curate_fingerprints,
            "judge_model": judge_model,
            "judge_mode": judge_mode,
        },
        "signal_versions": signal_versions,
        "cli_args": cli_args,
        # R-25 incremental summary は本 PR では空。後続で埋める。
        "incremental": {
            "input_records": input_records,
            "cache_hits_full": 0,
            "cache_hits_partial": 0,
            "newly_evaluated": input_records,
            "llm_calls_total": llm_calls_total,
            "llm_calls_saved_vs_full_rerun": 0,
            "cache_sources": [],
        },
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
