"""ComposeBackend 引数組み立てテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.orchestrator.backend import ComposeBackend
from joryu.orchestrator.profile import ModelProfile, ProfileSpec


def _profiles() -> dict[ModelProfile, ProfileSpec]:
    return {
        ModelProfile.DISTILL: ProfileSpec(
            name="distill", service="joryu", port=8100, compose_profile="distill"
        ),
        ModelProfile.SEED_GEN: ProfileSpec(
            name="seed_gen", service="joryu-seed", port=8110, compose_profile="seed_gen"
        ),
        ModelProfile.SCREENING: ProfileSpec(
            name="screening",
            service="joryu-judge",
            port=8080,
            kind="llama_server",
            compose_profile="screening",
        ),
    }


def test_compose_backend_start_profile(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        calls.append(cmd)
        return _Proc()

    backend = ComposeBackend(repo_root=str(tmp_path), docker_run=_run)
    spec = ProfileSpec(name="seed_gen", service="joryu-seed", port=8110, compose_profile="seed_gen")
    backend.start_profile(ModelProfile.SEED_GEN, spec=spec)
    assert calls[0][:6] == ["docker", "compose", "--profile", "always", "--profile", "seed_gen"]
    assert calls[0][-2:] == ["-d", "joryu-seed"]


def test_compose_backend_stop_profile_uses_docker_not_compose(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = "false"
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        calls.append(cmd)
        return _Proc()

    backend = ComposeBackend(repo_root=str(tmp_path), docker_run=_run)
    spec = ProfileSpec(name="distill", service="joryu", port=8100, compose_profile="distill")
    backend.stop_profile(ModelProfile.DISTILL, spec=spec)
    assert not any(c[:2] == ["docker", "compose"] for c in calls)
    assert calls[0][:4] == ["docker", "inspect", "-f", "{{.State.Running}}"]


def test_compose_backend_stop_other_gpu_profiles_calls_docker_stop(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    inspect_count = 0

    class _Proc:
        returncode = 0
        stdout = "true"
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        calls.append(cmd)
        nonlocal inspect_count
        if cmd[:3] == ["docker", "inspect", "-f"]:
            inspect_count += 1
            if inspect_count <= 2:
                return _Proc()
            proc = _Proc()
            proc.stdout = "false"
            return proc
        proc = _Proc()
        proc.stdout = "false"
        return proc

    backend = ComposeBackend(repo_root=str(tmp_path), docker_run=_run)
    backend.stop_other_gpu_profiles(ModelProfile.SEED_GEN, profiles=_profiles())
    assert not any(c[:2] == ["docker", "compose"] for c in calls)
    docker_stops = [c for c in calls if c[:2] == ["docker", "stop"]]
    assert "joryu" in {c[-1] for c in docker_stops}


def test_compose_backend_stop_logs_progress(tmp_path: Path) -> None:
    logs: list[str] = []

    class _Proc:
        returncode = 0
        stdout = "false"
        stderr = ""

    backend = ComposeBackend(
        repo_root=str(tmp_path),
        docker_run=lambda *_a, **_k: _Proc(),
    )
    backend._stop_gpu_service("joryu", log=logs.append)
    assert "[orchestrator] stopping container joryu" in logs
    assert "[orchestrator] stopped container joryu" in logs


def test_compose_backend_uses_resolved_host_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = tmp_path / "host-root"
    host.mkdir()
    cwds: list[str] = []

    class _Proc:
        returncode = 0
        stdout = "false"
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        if cmd[:2] == ["docker", "compose"]:
            cwds.append(str(kwargs.get("cwd", "")))
        return _Proc()

    monkeypatch.setattr(
        "joryu.orchestrator.backend.resolve_host_repo_root",
        lambda _root: host,
    )
    backend = ComposeBackend(repo_root=str(tmp_path / "container"), docker_run=_run)
    spec = ProfileSpec(name="seed_gen", service="joryu-seed", port=8110, compose_profile="seed_gen")
    backend.start_profile(ModelProfile.SEED_GEN, spec=spec)
    assert cwds == [str(host)]
