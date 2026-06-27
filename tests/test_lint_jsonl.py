"""scripts/lint_jsonl.py と CI タイムアウト設定のテスト (#273)。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_lint_jsonl_accepts_valid_fixture() -> None:
    fixture = REPO_ROOT / "tests" / "fixtures" / "jsonl" / "valid.jsonl"
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "lint_jsonl.py"), str(fixture)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr


def test_lint_jsonl_rejects_malformed_line(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('not-json\n{"ok": true}\n', encoding="utf-8")
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "lint_jsonl.py"), str(bad)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 1
    assert "invalid JSON" in rc.stderr


def test_lint_jsonl_rejects_non_object_line(tmp_path: Path) -> None:
    bad = tmp_path / "array.jsonl"
    bad.write_text("[1, 2, 3]\n", encoding="utf-8")
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "lint_jsonl.py"), str(bad)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 1
    assert "expected JSON object" in rc.stderr


def test_pre_commit_registers_lint_jsonl_hook() -> None:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "lint-jsonl" in config
    assert "lint_jsonl.py" in config


def test_ci_jobs_define_timeout_minutes() -> None:
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    ci = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    for job_name, job in ci["jobs"].items():
        assert "timeout-minutes" in job, f"job {job_name!r} missing timeout-minutes"
