"""docker_runtime.py: マウント準備と config 相対パス正規化。"""

from __future__ import annotations

from pathlib import Path

from joryu.docker_delegate import build_docker_command
from joryu.docker_runtime import container_config_rel, prepare_distill_docker_mounts


def test_container_config_rel_windows_absolute_string(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("distill:\n  styles_file: styles.yaml\n", encoding="utf-8")
    abs_ref = "C:/Users/dev/repo/config.yaml"
    assert container_config_rel(tmp_path, config_path.resolve(), abs_ref) == "config.yaml"


def test_container_config_rel_relative_passthrough(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("distill:\n  styles_file: styles.yaml\n", encoding="utf-8")
    assert container_config_rel(tmp_path, config_path.resolve(), "config.yaml") == "config.yaml"


def test_prepare_distill_docker_mounts_normalizes_absolute_config_rel(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("distill:\n  styles_file: styles.yaml\n", encoding="utf-8")
    abs_ref = str(config_path.resolve()).replace("\\", "/")

    mounts = prepare_distill_docker_mounts(
        tmp_path,
        config_path.resolve(),
        config_rel=abs_ref,
        mount_styles=False,
    )
    assert mounts.config_rel == "config.yaml"


def test_prepare_distill_docker_mounts_includes_tools_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "distill:\n  styles_file: styles.yaml\n  tools_file: tools.yaml\n",
        encoding="utf-8",
    )
    (tmp_path / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")

    mounts = prepare_distill_docker_mounts(
        tmp_path,
        config_path.resolve(),
        mount_styles=False,
    )
    assert mounts.tools_path is not None
    assert mounts.tools_path.resolve() == (tmp_path / "tools.yaml").resolve()
    assert mounts.tools_rel == "tools.yaml"


def test_build_docker_command_rejects_windows_absolute_container_path(tmp_path: Path) -> None:
    """絶対 config_rel が正規化されていればマウント先にドライブレターが入らない。"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("x: 1\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = tmp_path / "data"

    cmd = build_docker_command(
        image="joryu:test",
        cwd=tmp_path,
        config_path=config_path,
        config_rel="config.yaml",
        src_dir=src_dir,
        data_dir=data_dir,
        hf_cache=tmp_path / "hf",
        extra_args=[],
        cli_module="joryu.cli.probe_vllm",
        native_flag="--no-docker",
    )

    flat = " ".join(cmd)
    assert f"{config_path}:/app/config.yaml:ro" in flat
    assert ":/app/C:" not in flat
    assert "--config" in cmd
    idx = cmd.index("--config")
    assert cmd[idx + 1] == "config.yaml"
