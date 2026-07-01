"""API 起動時 compose preflight。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.api.app import create_app
from joryu.compose_invoke import ComposeProject

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_create_app_validates_compose_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    project = ComposeProject(
        host_root=REPO_ROOT,
        compose_file=REPO_ROOT / "docker-compose.yml",
    )
    monkeypatch.setattr("joryu.api.app.should_validate_compose_at_startup", lambda: True)
    monkeypatch.setattr("joryu.api.app.resolve_compose_project", lambda _r: project)
    monkeypatch.setattr(
        "joryu.api.app.assert_compose_contract_from_file",
        lambda f: calls.append(f"contract:{f}"),
    )
    monkeypatch.setattr(
        "joryu.api.app.validate_compose_profiles",
        lambda _p, prof: calls.append(f"profiles:{prof}"),
    )
    create_app(repo_root=REPO_ROOT)
    assert any(c.startswith("contract:") for c in calls)
    assert any(c.startswith("profiles:") for c in calls)
