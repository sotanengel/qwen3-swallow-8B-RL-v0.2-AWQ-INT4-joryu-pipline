"""compose_invoke: プロジェクト解決と契約検証。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from joryu.api.app import create_app
from joryu.compose_invoke import (
    ComposeProject,
    assert_compose_contract,
    assert_compose_contract_from_file,
    compose_command_prefix,
    resolve_compose_project,
    should_validate_compose_at_startup,
    validate_compose_profiles,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_resolve_compose_project_uses_host_compose_file(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    project = resolve_compose_project(tmp_path)
    assert project.compose_file == compose.resolve()
    assert project.host_root == tmp_path.resolve()
    assert project.local_compose_file == compose.resolve()


def test_resolve_compose_project_windows_host_path_inside_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    compose = workspace / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.chdir(app_dir)
    project = resolve_compose_project(
        workspace,
        env={
            "JORYU_REPO_ROOT": str(workspace),
            "JORYU_HOST_REPO_ROOT": "C:/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline",
        },
    )
    assert project.local_compose_file == compose.resolve()
    assert project.compose_file.as_posix() == (
        "C:/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/docker-compose.yml"
    )
    assert project.host_root.as_posix() == "C:/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline"
    assert project.compose_cwd == str(workspace)


def test_resolve_compose_project_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="compose file not found"):
        resolve_compose_project(tmp_path)


def test_compose_command_prefix_includes_absolute_compose_file(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    project = resolve_compose_project(tmp_path)
    assert compose_command_prefix(project) == [
        "docker",
        "compose",
        "-f",
        compose.resolve().as_posix(),
    ]


def test_resolve_compose_project_uses_mountinfo_host_path_with_local_bind_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API コンテナ再現: /workspace に compose、9p が C:/host/repo を返す。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.chdir(app_dir)
    monkeypatch.setattr(
        "joryu.compose_invoke.resolve_host_repo_root",
        lambda _root, **_: Path("C:/host/repo"),
    )
    project = resolve_compose_project(workspace, env={"JORYU_REPO_ROOT": str(workspace)})
    assert project.local_compose_file == (workspace / "docker-compose.yml").resolve()
    assert project.compose_file.as_posix() == "C:/host/repo/docker-compose.yml"
    assert "/app/C:" not in project.compose_file.as_posix()


def test_create_app_compose_preflight_with_9p_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_app が resolve_compose_project をモックせず通る (本番 preflight 経路)。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docker-compose.yml").write_text("services:\n  api: {}\n", encoding="utf-8")
    (workspace / "config.yaml").write_text("model:\n  name: test\n", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.chdir(app_dir)
    monkeypatch.setattr("joryu.api.app.should_validate_compose_at_startup", lambda: True)
    monkeypatch.setattr(
        "joryu.compose_invoke.resolve_host_repo_root",
        lambda _root, **_: Path("C:/host/repo"),
    )
    monkeypatch.setattr("joryu.api.app.validate_compose_profiles", lambda *_a, **_k: None)
    create_app(repo_root=workspace)


def test_assert_compose_contract_rejects_api_gpu_depends_on() -> None:
    compose = {
        "services": {
            "api": {"depends_on": ["joryu-seed"]},
        }
    }
    with pytest.raises(ValueError, match="GPU profile services"):
        assert_compose_contract(compose)


def test_assert_compose_contract_accepts_list_depends_on_without_gpu() -> None:
    assert_compose_contract({"services": {"api": {"depends_on": ["dashboard"]}}})


def test_assert_compose_contract_skips_when_api_missing() -> None:
    assert_compose_contract({"services": {}})


def test_assert_compose_contract_from_repo_file() -> None:
    assert_compose_contract_from_file(REPO_ROOT / "docker-compose.yml")


def test_compose_file_has_explicit_project_name() -> None:
    """name: がないとホスト/コンテナでプロジェクト名が分岐しネットワーク不達になる。"""
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose.get("name"), "docker-compose.yml must declare a top-level 'name:'"


def test_compose_volumes_have_fixed_names() -> None:
    """volume は name: を明示しないとプロジェクト名でスコープされ HF キャッシュが失われる。"""
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    volumes = compose.get("volumes") or {}
    for vol_key in ("hf-cache", "gguf-cache"):
        assert vol_key in volumes, f"volume {vol_key!r} must exist in docker-compose.yml"
        vol_def = volumes[vol_key] or {}
        assert vol_def.get("name") == vol_key, (
            f"volume {vol_key!r} must declare `name: {vol_key}` to avoid project-name scoping"
        )


def test_validate_compose_profiles_invokes_docker_config(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(yaml.safe_dump({"services": {}}), encoding="utf-8")
    project = ComposeProject(host_root=tmp_path, compose_file=compose)
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        calls.append(cmd)
        return _Proc()

    validate_compose_profiles(project, ("always", "seed_gen"), docker_run=_run)
    assert calls[0][:4] == ["docker", "compose", "-f", compose.as_posix()]
    assert calls[0][-1] == "config"
    assert "--profile" in calls[0]


def test_validate_compose_profiles_raises_on_failure(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    project = ComposeProject(host_root=tmp_path, compose_file=compose)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "invalid service reference"

    with pytest.raises(RuntimeError, match="compose config failed"):
        validate_compose_profiles(
            project, ("always", "seed_gen"), docker_run=lambda *_a, **_k: _Proc()
        )


def test_should_validate_compose_at_startup_skips_pytest_and_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    assert not should_validate_compose_at_startup(env={"PYTEST_CURRENT_TEST": "x"})
    assert not should_validate_compose_at_startup(env={"JORYU_ORCHESTRATOR_BACKEND": "fake"})
    assert should_validate_compose_at_startup(env={})
