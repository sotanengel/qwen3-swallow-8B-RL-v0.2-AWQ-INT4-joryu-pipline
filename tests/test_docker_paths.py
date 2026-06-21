"""docker_paths.py のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.docker_paths import map_path_for_docker, resolve_host_repo_root

_BIND_MOUNTINFO = """
123 456 0:1 / /workspace rw,relatime - fakeowner /host_mnt/c/Users/dev/repo rw
"""

_9P_MOUNTINFO = """
532 523 0:68 /qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline /workspace rw,noatime \
- 9p C:\\134 rw,aname=drvfs;path=C:\\;uid=0;gid=0;metadata
"""


def test_resolve_host_repo_root_from_env() -> None:
    root = resolve_host_repo_root(
        Path("/workspace"),
        env={"JORYU_HOST_REPO_ROOT": "C:/repo"},
    )
    assert root == Path("C:/repo")


def test_resolve_host_repo_root_from_bind_mountinfo() -> None:
    root = resolve_host_repo_root(
        Path("/workspace"),
        env={"JORYU_REPO_ROOT": "/workspace"},
        mountinfo_reader=lambda: _BIND_MOUNTINFO,
    )
    assert root == Path("/host_mnt/c/Users/dev/repo")


def test_resolve_host_repo_root_from_9p_mountinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("joryu.docker_paths.os.name", "posix")
    root = resolve_host_repo_root(
        Path("/workspace"),
        env={"JORYU_REPO_ROOT": "/workspace"},
        mountinfo_reader=lambda: _9P_MOUNTINFO,
    )
    assert root == Path("/run/desktop/mnt/host/c/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline")


def test_map_path_for_docker_translates_under_workspace() -> None:
    host_root = Path("/run/desktop/mnt/host/c/Users/dev/repo")
    mapped = map_path_for_docker(
        Path("/workspace/config.yaml"),
        repo_root=Path("/workspace"),
        host_repo_root=host_root,
        env={"JORYU_REPO_ROOT": "/workspace"},
    )
    assert mapped == host_root / "config.yaml"


def test_map_path_for_docker_falls_back_without_mapping() -> None:
    path = Path("/etc/hosts")
    assert (
        map_path_for_docker(
            path,
            repo_root=Path("/workspace"),
            host_repo_root=Path("/host/repo"),
            env={"JORYU_REPO_ROOT": "/workspace"},
        )
        == path.resolve()
    )
