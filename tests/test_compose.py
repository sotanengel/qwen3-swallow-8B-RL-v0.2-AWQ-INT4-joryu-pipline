"""compose.py: docker compose コマンド構築のユニットテスト。"""

from __future__ import annotations

import pytest

from joryu.compose import (
    build_artifact_cleanup_commands,
    builder_prune_command,
    compose_build_command,
    compose_down_command,
    compose_stop_command,
    compose_up_command,
    image_prune_command,
    run_pre_browser_image_cleanup,
    run_up_startup_cleanup,
)


def test_build_single_service() -> None:
    cmd = compose_build_command(services=["dashboard"])
    assert cmd == ["docker", "compose", "build", "dashboard"]


def test_build_multiple_services() -> None:
    cmd = compose_build_command(services=["dashboard", "joryu"])
    assert cmd == ["docker", "compose", "build", "dashboard", "joryu"]


def test_up_with_compose_profiles() -> None:
    cmd = compose_up_command(
        services=["dashboard", "api", "joryu"],
        detach=True,
        build=False,
        profiles=["always", "distill"],
    )
    assert cmd[:7] == [
        "docker",
        "compose",
        "--profile",
        "always",
        "--profile",
        "distill",
        "up",
    ]
    assert "-d" in cmd


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


def test_stop_single_service() -> None:
    cmd = compose_stop_command(services=["joryu"])
    assert cmd == ["docker", "compose", "stop", "joryu"]


def test_down_default() -> None:
    cmd = compose_down_command(volumes=False)
    assert cmd == ["docker", "compose", "down"]


def test_down_with_volumes() -> None:
    cmd = compose_down_command(volumes=True)
    assert "-v" in cmd or "--volumes" in cmd


def test_builder_prune_command_is_all_and_force() -> None:
    """build キャッシュ累積防止のため `-a -f` で current image 参照外の全 cache を回収する。

    `-f` 単独では dangling layer しか落ちず、旧世代の reusable cache が
    積み上がるため `-a` を付けて current image 群から参照されていない
    キャッシュも一掃する。
    """
    assert builder_prune_command() == ["docker", "builder", "prune", "-a", "-f"]


def test_image_prune_command_is_force() -> None:
    """disk 不足時の自動回収で dangling image を `-f` で削除する。"""
    assert image_prune_command() == ["docker", "image", "prune", "-f"]


def test_build_artifact_cleanup_commands() -> None:
    """build 後 cleanup は dangling image と旧 build cache を順に回収する。"""
    assert build_artifact_cleanup_commands() == [
        ["docker", "image", "prune", "-f"],
        ["docker", "builder", "prune", "-a", "-f"],
    ]


def test_run_up_startup_cleanup_prunes_dangling_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """起動時 cleanup は dangling image のみ削除する。"""
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)

        class _Done:
            returncode = 0

        return _Done()

    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    run_up_startup_cleanup()
    assert calls == [image_prune_command()]


def test_run_pre_browser_image_cleanup_prunes_dangling_only(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ブラウザ起動直前 cleanup は dangling image のみ削除する。"""
    import logging

    caplog.set_level(logging.INFO, logger="joryu.compose")
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)

        class _Done:
            returncode = 0

        return _Done()

    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    run_pre_browser_image_cleanup()
    assert calls == [image_prune_command()]
    assert any("before opening browser" in r.message for r in caplog.records)


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
