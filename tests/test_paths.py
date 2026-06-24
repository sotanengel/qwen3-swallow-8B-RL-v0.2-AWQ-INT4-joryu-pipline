"""paths.py: 共通パス解決ヘルパ。"""

from __future__ import annotations

from pathlib import Path

from joryu.paths import resolve_config_relative


def test_resolve_config_relative_from_config_parent(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    config_path = cfg_dir / "config.yaml"
    config_path.write_text("x: 1\n", encoding="utf-8")
    tools = cfg_dir / "tools.yaml"
    tools.write_text("tools: {}\n", encoding="utf-8")

    resolved = resolve_config_relative(config_path, "tools.yaml")
    assert resolved == tools.resolve()


def test_resolve_config_relative_absolute_passthrough(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("x: 1\n", encoding="utf-8")
    abs_tools = tmp_path / "custom-tools.yaml"
    abs_tools.write_text("tools: {}\n", encoding="utf-8")

    resolved = resolve_config_relative(config_path, str(abs_tools.resolve()))
    assert resolved == abs_tools.resolve()
