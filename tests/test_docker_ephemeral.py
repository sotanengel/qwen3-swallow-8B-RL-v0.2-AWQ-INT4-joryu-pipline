"""Docker 一時コンテナの命名と孤児コンテナ停止。"""

from __future__ import annotations

from pathlib import Path

from joryu.docker_delegate import (
    JORYU_COMPOSE_CONTAINER_NAMES,
    JORYU_DISTILL_HOST_CONTAINER,
    JORYU_PROBE_CONTAINER,
    build_docker_command,
    is_managed_joryu_container,
    remove_foreign_project_joryu_containers,
    stop_orphan_joryu_containers,
)


def test_build_docker_command_includes_container_name(tmp_path: Path) -> None:
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
        extra_args=["--count", "1"],
        container_name=JORYU_PROBE_CONTAINER,
    )

    idx = cmd.index("--name")
    assert cmd[idx + 1] == JORYU_PROBE_CONTAINER
    assert cmd.index("--name") < cmd.index("--gpus")


def test_is_managed_joryu_container() -> None:
    assert is_managed_joryu_container("joryu")
    assert is_managed_joryu_container("joryu-api")
    assert is_managed_joryu_container("joryu-seed")
    assert is_managed_joryu_container("joryu-judge")
    assert is_managed_joryu_container("joryu-job")
    assert is_managed_joryu_container("joryu-mcp")
    assert is_managed_joryu_container("joryu-dashboard")
    assert is_managed_joryu_container("joryu-job-abc123")
    assert is_managed_joryu_container(JORYU_PROBE_CONTAINER)
    assert is_managed_joryu_container(JORYU_DISTILL_HOST_CONTAINER)
    assert not is_managed_joryu_container("intelligent_jemison")
    assert not is_managed_joryu_container("compassionate_mccarthy")


def test_stop_orphan_joryu_containers_stops_auto_named_only(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)

        class _Done:
            returncode = 0
            stdout = ""

        if cmd[:3] == ["docker", "ps", "-q"]:
            _Done.stdout = "cid1\ncid2\n"
        elif cmd[:3] == ["docker", "inspect", "-f"]:
            if "cid1" in cmd:
                _Done.stdout = "/intelligent_jemison"
            else:
                _Done.stdout = "/joryu"
        return _Done()

    stop_orphan_joryu_containers(docker_run=fake_run)
    assert ["docker", "stop", "--time", "10", "cid1"] in calls
    assert not any(c[:3] == ["docker", "stop"] and "cid2" in c for c in calls)


def _foreign_project_fake_run(labels: dict[str, str | None]) -> tuple[list[list[str]], object]:
    """labels: container_name -> compose.project label (None = 存在しない)。"""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)

        class _Done:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:2] == ["docker", "inspect"]:
            name = cmd[-1]
            label = labels.get(name)
            if label is None:
                _Done.returncode = 1  # 存在しない
                _Done.stdout = ""
            else:
                _Done.stdout = label + "\n"
            return _Done()
        if cmd[:3] == ["docker", "rm", "-f"]:
            return _Done()
        return _Done()

    return calls, fake_run


def test_remove_foreign_project_joryu_containers_removes_foreign() -> None:
    labels = {name: None for name in JORYU_COMPOSE_CONTAINER_NAMES}
    labels["joryu-mcp"] = "workspace"  # 別プロジェクト
    labels["joryu-api"] = "joryu"  # 現プロジェクト
    labels["joryu-seed"] = ""  # ラベルなし (compose 外)

    calls, fake_run = _foreign_project_fake_run(labels)
    logs: list[str] = []
    remove_foreign_project_joryu_containers(docker_run=fake_run, log=logs.append)

    rm_calls = [c for c in calls if c[:3] == ["docker", "rm", "-f"]]
    assert rm_calls == [["docker", "rm", "-f", "joryu-mcp"]]
    assert any("foreign-project container joryu-mcp" in line for line in logs)
    assert any("project=workspace" in line for line in logs)


def test_remove_foreign_project_joryu_containers_keeps_current_project() -> None:
    labels = {name: None for name in JORYU_COMPOSE_CONTAINER_NAMES}
    labels["joryu-api"] = "joryu"
    labels["joryu-dashboard"] = "joryu"

    calls, fake_run = _foreign_project_fake_run(labels)
    remove_foreign_project_joryu_containers(docker_run=fake_run)

    assert not [c for c in calls if c[:3] == ["docker", "rm", "-f"]]


def test_remove_foreign_project_joryu_containers_keeps_unlabeled() -> None:
    labels = {name: None for name in JORYU_COMPOSE_CONTAINER_NAMES}
    labels["joryu-mcp"] = ""  # compose 管理外の手動 docker run

    calls, fake_run = _foreign_project_fake_run(labels)
    remove_foreign_project_joryu_containers(docker_run=fake_run)

    assert not [c for c in calls if c[:3] == ["docker", "rm", "-f"]]


def test_remove_foreign_project_joryu_containers_skips_absent() -> None:
    labels: dict[str, str | None] = {name: None for name in JORYU_COMPOSE_CONTAINER_NAMES}

    calls, fake_run = _foreign_project_fake_run(labels)
    remove_foreign_project_joryu_containers(docker_run=fake_run)

    assert not [c for c in calls if c[:3] == ["docker", "rm", "-f"]]
