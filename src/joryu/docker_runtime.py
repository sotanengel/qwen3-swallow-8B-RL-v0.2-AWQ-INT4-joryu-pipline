"""Docker 蒸留実行前のマウント準備。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from joryu.config import load_config
from joryu.docker_delegate import hf_cache_dir
from joryu.paths import dashboard_public


@dataclass
class DockerMountContext:
    """`build_docker_command` に渡すマウントパス群。"""

    config_path: Path
    config_rel: str
    data_dir: Path
    dashboard_public: Path
    src_dir: Path
    hf_cache: Path | str
    styles_path: Path | None
    styles_rel: str | None


def resolve_styles_mount(config_path: Path, styles_rel: str) -> Path | None:
    """styles.yaml の実パス。存在しなければ None。"""
    candidate = (config_path.parent / styles_rel).resolve()
    return candidate if candidate.exists() else None


def prepare_distill_docker_mounts(
    repo_root: Path,
    config_path: Path,
    *,
    config_rel: str | None = None,
    map_path: Callable[[Path], Path] | None = None,
    hf_cache: Path | str | None = None,
    mount_styles: bool = True,
) -> DockerMountContext:
    """data/dashboard/public/src/HF cache/styles を整備しマウント用パスを返す。"""
    _map = map_path or (lambda p: p)
    resolved_config = config_path.resolve()
    rel = (config_rel or str(config_path)).replace("\\", "/")

    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    public_dir = dashboard_public(repo_root)
    src_dir = (repo_root / "src").resolve()

    cfg = load_config(resolved_config)
    styles_path: Path | None = None
    styles_rel: str | None = None
    if mount_styles:
        styles_rel = cfg.distill.styles_file
        styles_path = resolve_styles_mount(resolved_config, styles_rel)

    if hf_cache is None:
        hf_cache_path = hf_cache_dir()
        hf_cache_path.mkdir(parents=True, exist_ok=True)
        resolved_hf_cache: Path | str = _map(hf_cache_path)
    else:
        resolved_hf_cache = hf_cache

    return DockerMountContext(
        config_path=_map(resolved_config),
        config_rel=rel,
        data_dir=_map(data_dir),
        dashboard_public=_map(public_dir),
        src_dir=_map(src_dir),
        hf_cache=resolved_hf_cache,
        styles_path=_map(styles_path) if styles_path is not None else None,
        styles_rel=styles_rel if styles_path is not None else None,
    )
