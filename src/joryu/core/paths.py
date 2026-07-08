"""リポジトリ内の共通パス定数と解決ヘルパ。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from joryu.core.config import Config, load_config

DEFAULT_CONFIG = "config.yaml"
DASHBOARD_PUBLIC_DIR = "dashboard/public"
STATS_JSON_REL = f"{DASHBOARD_PUBLIC_DIR}/stats.json"
CURATION_JSON_REL = f"{DASHBOARD_PUBLIC_DIR}/curation.json"
SCREENING_JSON_REL = f"{DASHBOARD_PUBLIC_DIR}/screening.json"
RESPONSES_JSONL_REL = f"{DASHBOARD_PUBLIC_DIR}/responses.jsonl"
CURATED_RESPONSES_JSONL_REL = f"{DASHBOARD_PUBLIC_DIR}/responses.high_quality.jsonl"
HIGH_QUALITY_JSONL_NAME = "responses.high_quality.jsonl"


def resolve_optional_config(path: str | Path) -> Config:
    """設定ファイルが存在すれば読み込み、なければ既定 Config を返す。"""
    p = Path(path)
    return load_config(p) if p.exists() else Config()


def resolve_distill_output(cfg: Config, input_arg: str | Path | None) -> Path:
    """CLI 共通: 蒸留 JSONL 入力パスを解決する。"""
    if input_arg:
        return Path(input_arg)
    return Path(cfg.distill.out_dir) / cfg.distill.out_file


def resolve_config_relative(config_path: Path, rel: str) -> Path:
    """config.yaml の親ディレクトリ基準で相対パスを絶対パスに解決する。"""
    p = Path(rel)
    if p.is_absolute():
        return p.resolve()
    return (config_path.parent / p).resolve()


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


def resolve_cli_config_path(config_rel: str, *, cwd: Path | None = None) -> Path:
    """CLI 用 config.yaml の絶対パス。JORYU_REPO_ROOT 未設定時は cwd (Docker では /app)。"""
    p = Path(config_rel)
    if p.is_absolute():
        return p.resolve()
    root = resolve_repo_root() or cwd or Path.cwd()
    return (root / config_rel).resolve()


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


def resolve_curated_high_quality_jsonl(repo_root: Path) -> Path | None:
    """curation.json の ``_meta.source_path`` から high_quality JSONL を解決する。

    ``source_path`` は通常 ``scores.jsonl`` を指す。同ディレクトリの
    ``responses.high_quality.jsonl`` を返す。解決できなければ
    ``dashboard/public/responses.high_quality.jsonl`` にフォールバックする。
    """
    curation_path = repo_root / CURATION_JSON_REL
    if curation_path.is_file():
        try:
            data = json.loads(curation_path.read_text(encoding="utf-8"))
            meta = data.get("_meta") if isinstance(data, dict) else None
            source_raw = meta.get("source_path") if isinstance(meta, dict) else None
            if isinstance(source_raw, str) and source_raw.strip():
                scores_path = Path(source_raw)
                if not scores_path.is_absolute():
                    scores_path = (repo_root / scores_path).resolve()
                candidate = scores_path.parent / HIGH_QUALITY_JSONL_NAME
                if candidate.is_file():
                    return candidate
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    public = repo_root / CURATED_RESPONSES_JSONL_REL
    return public if public.is_file() else None
