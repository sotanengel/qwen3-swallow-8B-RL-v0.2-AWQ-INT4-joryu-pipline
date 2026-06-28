"""orchestrator factory テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.config import Config, ModelsConfig
from joryu.orchestrator.factory import (
    auto_restore_profile,
    build_orchestrator,
    profile_specs_from_config,
)
from joryu.orchestrator.profile import ModelProfile


def test_profile_specs_from_config_defaults() -> None:
    cfg = Config()
    specs = profile_specs_from_config(cfg)
    assert ModelProfile.DISTILL in specs
    assert specs[ModelProfile.SEED_GEN].port == 8110


def test_auto_restore_none() -> None:
    cfg = Config(models=ModelsConfig(auto_restore="none"))
    assert auto_restore_profile(cfg) is None


def test_build_orchestrator_fake_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_ORCHESTRATOR_BACKEND", "fake")
    orch = build_orchestrator(tmp_path)
    assert orch.profiles[ModelProfile.SCREENING].kind == "llama_server"
