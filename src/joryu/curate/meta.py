"""curation_meta.json 出力 (R-17 / R-25)。"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


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
    incremental: dict[str, Any] | None = None,
) -> Path:
    """`curation_meta.json` を書き出してそのパスを返す。

    `incremental` は R-25 の差分実行サマリ (`cache_hits_full` 等)。
    None の場合は MVP 互換のダミー (全件 newly_evaluated) を入れる。
    """
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    out = dst / "curation_meta.json"
    if incremental is None:
        incremental = {
            "input_records": input_records,
            "cache_hits_full": 0,
            "cache_hits_partial": 0,
            "newly_evaluated": input_records,
            "llm_calls_total": llm_calls_total,
            "llm_calls_saved_vs_full_rerun": 0,
            "cache_sources": [],
        }
    # llm_calls_saved_vs_full_rerun は incremental 内で計算 (受け取り側との整合性確保)
    if "llm_calls_saved_vs_full_rerun" not in incremental:
        incremental["llm_calls_saved_vs_full_rerun"] = incremental.get("llm_calls_saved", 0)
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
        "incremental": incremental,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def format_incremental_summary(incremental: dict[str, Any]) -> str:
    """`incremental` セクションを人間可読な複数行文字列に整形する (R-25 stderr 用)。"""
    lines = ["==== 差分実行サマリ (R-25) ===="]
    lines.append(f"入力レコード数        : {incremental.get('input_records', 0)}")
    lines.append(f"  キャッシュ完全再利用  : {incremental.get('cache_hits_full', 0)}")
    lines.append(f"  キャッシュ部分再利用  : {incremental.get('cache_hits_partial', 0)}")
    lines.append(f"  新規評価              : {incremental.get('newly_evaluated', 0)}")
    lines.append(f"LLM 呼び出し           : {incremental.get('llm_calls_total', 0)} 回")
    lines.append(
        f"LLM 削減 (vs full rerun): {incremental.get('llm_calls_saved_vs_full_rerun', 0)} 回"
    )
    if incremental.get("rescore_only_misses"):
        lines.append(f"  rescore-only 未ヒット  : {incremental['rescore_only_misses']}")
    if incremental.get("resume_skipped"):
        lines.append(f"  resume スキップ        : {incremental['resume_skipped']}")
    sources = incremental.get("cache_sources") or []
    if sources:
        lines.append("キャッシュソース:")
        for s in sources:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def print_incremental_summary(incremental: dict[str, Any], *, stream: TextIO | None = None) -> None:
    """integer 整形した差分実行サマリを stderr に出す (R-25)。"""
    text = format_incremental_summary(incremental)
    out = stream if stream is not None else sys.stderr
    out.write(text + "\n")
