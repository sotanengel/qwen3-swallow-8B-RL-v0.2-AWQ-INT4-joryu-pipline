"""curate ラン成果物の検索ヘルパ。"""

from __future__ import annotations

from pathlib import Path


def find_latest_run_artifact(
    parent: Path,
    *,
    exclude: Path,
    marker: str,
) -> Path | None:
    """`parent` 直下の run ディレクトリから `marker` ファイルを持つ最新パスを返す。"""
    if not parent.exists() or not parent.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    exclude_resolved = exclude.resolve()
    for child in parent.iterdir():
        if not child.is_dir() or child.resolve() == exclude_resolved:
            continue
        artifact = child / marker
        if artifact.exists():
            candidates.append((artifact.stat().st_mtime, artifact))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]
