"""config パス解決と env 上書き (#259)。"""

from __future__ import annotations

import os
from pathlib import Path

from joryu.paths import DEFAULT_CONFIG, resolve_repo_root


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    """CLI / API 共通の config パス解決。"""
    env_path = os.environ.get("JORYU_CONFIG", "").strip()
    if config_path is not None:
        return Path(config_path).resolve()
    if env_path:
        return Path(env_path).resolve()
    root = resolve_repo_root()
    if root is not None:
        return (root / DEFAULT_CONFIG).resolve()
    return Path(DEFAULT_CONFIG).resolve()


__all__ = ["resolve_config_path"]
