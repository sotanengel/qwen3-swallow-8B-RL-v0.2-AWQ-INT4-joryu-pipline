"""docker_delegate.py: Windows → Docker 自動デリゲートの分岐と argv 構築。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.docker_delegate import build_docker_command, should_use_docker


def test_force_docker_wins() -> None:
    assert should_use_docker(force_docker=True, force_native=False, system="Linux") is True


def test_force_native_wins() -> None:
    assert should_use_docker(force_docker=False, force_native=True, system="Windows") is False


def test_auto_uses_docker_on_windows() -> None:
    assert should_use_docker(force_docker=False, force_native=False, system="Windows") is True


def test_auto_native_on_linux() -> None:
    assert should_use_docker(force_docker=False, force_native=False, system="Linux") is False


def test_env_var_disables_auto_docker() -> None:
    assert (
        should_use_docker(
            force_docker=False, force_native=False, system="Windows", env={"JORYU_NO_DOCKER": "1"}
        )
        is False
    )


def test_build_docker_command_contains_expected_mounts(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: {}\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = tmp_path / "data"
    dashboard_public = tmp_path / "dashboard" / "public"
    dashboard_public.mkdir(parents=True)
    hf_cache = tmp_path / "hf"

    cmd = build_docker_command(
        image="joryu:test",
        cwd=tmp_path,
        config_path=config_path,
        config_rel="config.yaml",
        src_dir=src_dir,
        data_dir=data_dir,
        dashboard_public_dir=dashboard_public,
        hf_cache=hf_cache,
        extra_args=["--count", "1"],
    )

    assert cmd[0] == "docker"
    assert "--gpus" in cmd and "all" in cmd
    # マウント
    flat = " ".join(cmd)
    assert f"{data_dir}:/app/data" in flat
    assert f"{dashboard_public}:/app/dashboard/public" in flat
    assert f"{config_path}:/app/config.yaml:ro" in flat
    assert f"{src_dir}:/app/src:ro" in flat
    assert f"{hf_cache}:/root/.cache/huggingface" in flat
    assert "joryu:test" in cmd


def test_build_docker_command_mounts_styles_when_provided(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: {}\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = tmp_path / "data"
    hf_cache = tmp_path / "hf"
    styles_path = tmp_path / "styles.yaml"
    styles_path.write_text("styles: {}\n", encoding="utf-8")

    cmd = build_docker_command(
        image="joryu:test",
        cwd=tmp_path,
        config_path=config_path,
        config_rel="config.yaml",
        src_dir=src_dir,
        data_dir=data_dir,
        hf_cache=hf_cache,
        styles_path=styles_path,
        styles_rel="styles.yaml",
        extra_args=["--style", "prose"],
    )

    flat = " ".join(cmd)
    assert f"{styles_path}:/app/styles.yaml:ro" in flat
    # コンテナ内コマンドは joryu-distill --no-docker (再起防止)
    assert "joryu.cli.distill" in flat or "joryu-distill" in flat
    assert "--no-docker" in cmd
    assert "--config" in cmd
    assert "--style" in cmd and "prose" in cmd


def test_build_docker_command_mounts_tools_when_provided(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: {}\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = tmp_path / "data"
    hf_cache = tmp_path / "hf"
    tools_path = tmp_path / "tools.yaml"
    tools_path.write_text("tools: {}\n", encoding="utf-8")

    cmd = build_docker_command(
        image="joryu:test",
        cwd=tmp_path,
        config_path=config_path,
        config_rel="config.yaml",
        src_dir=src_dir,
        data_dir=data_dir,
        hf_cache=hf_cache,
        tools_path=tools_path,
        tools_rel="tools.yaml",
        extra_args=["--tool-ids", "search"],
    )

    flat = " ".join(cmd)
    assert f"{tools_path}:/app/tools.yaml:ro" in flat


def test_run_in_docker_captures_stderr_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """returncode != 0 のとき subprocess stderr が capture され logging に記録される。"""
    import logging

    from joryu import docker_delegate

    caplog.set_level(logging.WARNING, logger="joryu.docker_delegate")

    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: {}\ndistill:\n  styles_file: styles.yaml\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "styles.yaml").write_text("styles: {}\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    def fake_run(cmd, **kwargs):
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True
        return type(
            "Proc",
            (),
            {"returncode": 1, "stdout": "", "stderr": "docker-stderr-marker\n"},
        )()

    monkeypatch.setattr(docker_delegate.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_delegate, "stop_docker_container", lambda *_a, **_k: None)

    rc = docker_delegate.run_in_docker(
        config="config.yaml",
        extra_args=["--count", "1"],
    )
    assert rc == 1
    assert any("docker-stderr-marker" in r.message for r in caplog.records)


def test_build_docker_command_allocates_tty_when_requested(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model: {}\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = tmp_path / "data"
    hf_cache = tmp_path / "hf"

    cmd = build_docker_command(
        image="joryu:test",
        cwd=tmp_path,
        config_path=config_path,
        config_rel="config.yaml",
        src_dir=src_dir,
        data_dir=data_dir,
        hf_cache=hf_cache,
        allocate_tty=True,
        extra_args=["--count", "1"],
    )

    assert cmd[0:4] == ["docker", "run", "--rm", "-t"]
