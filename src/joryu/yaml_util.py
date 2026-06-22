"""YAML 読み込みの薄い共通層。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """YAML ファイルを mapping として読み込む。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        msg = f"{path}: root must be a mapping"
        raise ValueError(msg)
    return raw
