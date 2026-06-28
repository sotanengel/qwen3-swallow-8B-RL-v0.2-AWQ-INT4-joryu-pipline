"""ComposeBackend 引数組み立てテスト。"""

from __future__ import annotations

from pathlib import Path

from joryu.orchestrator.backend import ComposeBackend
from joryu.orchestrator.profile import ModelProfile, ProfileSpec


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
