"""compose_invoke: プロジェクト解決と契約検証。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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
        str(compose.resolve()),
    ]


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
    assert calls[0][:4] == ["docker", "compose", "-f", str(compose)]
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
