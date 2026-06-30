"""カバレッジ閾値と CI/pre-commit 用スクリプトの設定テスト。"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_coverage_threshold_configured_in_pyproject() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage = data["tool"]["coverage"]
    assert coverage["run"]["source"] == ["joryu"]
    assert coverage["report"]["fail_under"] >= 88


def test_check_coverage_script_exists_and_is_executable() -> None:
    script = REPO_ROOT / "scripts" / "check_coverage.sh"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "pytest" in content
    assert "cov" in content


def test_pre_commit_does_not_register_pre_push_hooks() -> None:
    """重い pytest/カバレッジは pre-push ではなく GitHub Actions に一任する。"""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "stages: [pre-push]" not in config
    assert "pytest-coverage" not in config
    assert "ci-gate-pre-push" not in config
    assert "default_install_hook_types: [pre-commit, pre-push]" not in config


def test_check_sh_runs_coverage_gate() -> None:
    script = (REPO_ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert "check_coverage.sh" in script


def test_ci_workflow_runs_coverage_and_verify() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "check_coverage.sh" in ci
    assert "verify_pipeline.sh" in ci
