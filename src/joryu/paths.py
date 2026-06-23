"""リポジトリ内の共通パス定数と解決ヘルパ。"""

from __future__ import annotations

import os
from pathlib import Path

from joryu.config import Config, load_config

DEFAULT_CONFIG = "config.yaml"
DASHBOARD_PUBLIC_DIR = "dashboard/public"
STATS_JSON_REL = f"{DASHBOARD_PUBLIC_DIR}/stats.json"
CURATION_JSON_REL = f"{DASHBOARD_PUBLIC_DIR}/curation.json"
RESPONSES_JSONL_REL = f"{DASHBOARD_PUBLIC_DIR}/responses.jsonl"


def resolve_optional_config(path: str | Path) -> Config:
    """設定ファイルが存在すれば読み込み、なければ既定 Config を返す。"""
    p = Path(path)
    return load_config(p) if p.exists() else Config()


def resolve_distill_output(cfg: Config, input_arg: str | Path | None) -> Path:
    """CLI 共通: 蒸留 JSONL 入力パスを解決する。"""
    if input_arg:
        return Path(input_arg)
    return Path(cfg.distill.out_dir) / cfg.distill.out_file


def resolve_repo_root(*, out_path: Path | None = None) -> Path | None:
    """stats.json 出力先を決めるリポジトリルートを返す。特定できなければ None。"""
    env = os.environ.get("JORYU_REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    if out_path is not None:
        resolved = out_path.resolve()
        if len(resolved.parts) >= 3 and resolved.parent.name == "distilled":
            return resolved.parent.parent.parent
    return None


def resolve_limits_probe_path(
    path: str | Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """limits_probe_file をリポジトリルート基準の絶対パスに解決する。"""
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    root = repo_root or resolve_repo_root() or Path.cwd()
    return (root / p).resolve()


def dashboard_public(repo_root: Path, *, mkdir: bool = True) -> Path:
    """dashboard/public の絶対パス。mkdir=True なら存在保証。"""
    path = repo_root / DASHBOARD_PUBLIC_DIR
    if mkdir:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_stats_output_path(
    *,
    out_path: Path | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """dashboard/public/stats.json の絶対パスを返す。特定できなければ None。"""
    root = repo_root or resolve_repo_root(out_path=out_path)
    if root is None:
        return None
    return root / STATS_JSON_REL
