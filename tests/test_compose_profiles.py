"""docker-compose profile 組み合わせの契約テスト (ADR 0005)。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

GPU_PROFILE_SERVICES = frozenset({"joryu", "joryu-seed", "joryu-judge"})
GPU_COMPOSE_PROFILES = ("distill", "seed_gen", "screening")


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def _depends_on_service_names(service: dict) -> set[str]:
    raw = service.get("depends_on") or {}
    if isinstance(raw, list):
        return set(raw)
    return set(raw)


def test_api_does_not_depend_on_gpu_profile_services() -> None:
    """api (always) は排他 GPU サービスに depends_on してはならない。"""
    compose = _load_compose()
    deps = _depends_on_service_names(compose["services"]["api"])
    overlap = deps & GPU_PROFILE_SERVICES
    assert not overlap, f"api depends_on must not reference GPU profile services: {overlap}"


@pytest.mark.parametrize("gpu_profile", GPU_COMPOSE_PROFILES)
def test_compose_config_valid_for_always_plus_gpu_profile(gpu_profile: str) -> None:
    """orchestrator が使う profile 組み合わせで compose config が通る。"""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI not available")
    proc = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "--profile",
            "always",
            "--profile",
            gpu_profile,
            "config",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()
