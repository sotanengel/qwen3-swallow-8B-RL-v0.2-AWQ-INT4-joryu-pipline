"""docker compose プロジェクト解決と契約検証 (joryu-up / orchestrator 共通)。"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from joryu.docker_paths import resolve_host_repo_root

logger = logging.getLogger(__name__)

COMPOSE_FILENAME = "docker-compose.yml"
GPU_PROFILE_SERVICES = frozenset({"joryu", "joryu-seed", "joryu-judge"})
GPU_COMPOSE_PROFILES = ("distill", "seed_gen", "screening")


@dataclass(frozen=True)
class ComposeProject:
    """ホスト上の compose プロジェクト (cwd + -f の唯一の正)。"""

    host_root: Path
    compose_file: Path

    @property
    def compose_file_flag(self) -> list[str]:
        return ["-f", str(self.compose_file)]


def resolve_compose_project(
    repo_root: Path,
    *,
    env: dict[str, str] | None = None,
) -> ComposeProject:
    """joryu-up と orchestrator が同じ compose 定義を使うよう host ルートを解決する。"""
    host_root = resolve_host_repo_root(repo_root, env=env).resolve()
    compose_file = (host_root / COMPOSE_FILENAME).resolve()
    if not compose_file.is_file():
        msg = f"compose file not found: {compose_file}"
        raise FileNotFoundError(msg)
    return ComposeProject(host_root=host_root, compose_file=compose_file)


def _depends_on_service_names(service: dict) -> set[str]:
    raw = service.get("depends_on") or {}
    if isinstance(raw, list):
        return set(raw)
    return set(raw)


def assert_compose_contract(compose: dict) -> None:
    """api (always) は排他 GPU サービスに depends_on してはならない。"""
    api = compose.get("services", {}).get("api")
    if not api:
        return
    deps = _depends_on_service_names(api)
    overlap = deps & GPU_PROFILE_SERVICES
    if overlap:
        msg = f"api depends_on must not reference GPU profile services: {overlap}"
        raise ValueError(msg)


def assert_compose_contract_from_file(compose_file: Path) -> None:
    compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    assert_compose_contract(compose)


def compose_command_prefix(project: ComposeProject) -> list[str]:
    return ["docker", "compose", *project.compose_file_flag]


def validate_compose_profiles(
    project: ComposeProject,
    profiles: tuple[str, ...],
    *,
    docker_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """orchestrator が使う profile 組み合わせで ``docker compose config`` が通ることを検証。"""
    cmd = compose_command_prefix(project)
    for profile in profiles:
        cmd.extend(["--profile", profile])
    cmd.append("config")
    proc = docker_run(
        cmd,
        cwd=str(project.host_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        msg = (
            f"compose config failed for profiles {profiles} (file={project.compose_file}): {stderr}"
        )
        raise RuntimeError(msg)


def should_validate_compose_at_startup(*, env: dict[str, str] | None = None) -> bool:
    """API 起動時の compose 検証を行うか (pytest / fake backend ではスキップ)。"""
    import sys

    if "pytest" in sys.modules:
        return False
    e = os.environ if env is None else env
    if e.get("JORYU_ORCHESTRATOR_BACKEND", "").lower() == "fake":
        return False
    if e.get("PYTEST_CURRENT_TEST"):
        return False
    return True
