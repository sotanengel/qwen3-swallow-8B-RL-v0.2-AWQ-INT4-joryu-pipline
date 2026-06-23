"""compose.py: docker compose コマンド構築のユニットテスト。"""

from __future__ import annotations

from joryu.compose import (
    builder_prune_command,
    compose_build_command,
    compose_down_command,
    compose_up_command,
)


def test_build_single_service() -> None:
    cmd = compose_build_command(services=["dashboard"])
    assert cmd == ["docker", "compose", "build", "dashboard"]


def test_build_multiple_services() -> None:
    cmd = compose_build_command(services=["dashboard", "joryu"])
    assert cmd == ["docker", "compose", "build", "dashboard", "joryu"]


def test_up_default_brings_up_full_stack_with_build() -> None:
    cmd = compose_up_command(services=None, detach=False, build=True)
    assert cmd[:3] == ["docker", "compose", "up"]
    assert "--build" in cmd
    assert "-d" not in cmd
    # 末尾にサービス名なし = フルスタック起動
    assert "dashboard" not in cmd
    assert "joryu" not in cmd


def test_up_detached_no_build() -> None:
    cmd = compose_up_command(services=None, detach=True, build=False)
    assert "-d" in cmd
    assert "--build" not in cmd


def test_up_frontend_only() -> None:
    cmd = compose_up_command(services=["dashboard"], detach=False, build=True)
    assert cmd[-1] == "dashboard"


def test_up_backend_only() -> None:
    cmd = compose_up_command(services=["joryu"], detach=False, build=True)
    assert cmd[-1] == "joryu"


def test_up_multiple_services() -> None:
    cmd = compose_up_command(services=["joryu", "dashboard"], detach=True, build=True)
    # 並びは入力順を保つ
    idx_j = cmd.index("joryu")
    idx_d = cmd.index("dashboard")
    assert idx_j < idx_d


def test_down_default() -> None:
    cmd = compose_down_command(volumes=False)
    assert cmd == ["docker", "compose", "down"]


def test_down_with_volumes() -> None:
    cmd = compose_down_command(volumes=True)
    assert "-v" in cmd or "--volumes" in cmd


def test_builder_prune_command_is_force() -> None:
    """build キャッシュ累積防止のため `-f` 付きで unused 層を回収する。"""
    assert builder_prune_command() == ["docker", "builder", "prune", "-f"]


def test_up_force_recreate_after_build() -> None:
    cmd = compose_up_command(
        services=["dashboard", "api"],
        detach=False,
        build=False,
        force_recreate=True,
    )
    assert cmd == [
        "docker",
        "compose",
        "up",
        "--force-recreate",
        "dashboard",
        "api",
    ]
