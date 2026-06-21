"""preflight.py: git 差分映射とディスク preflight のユニットテスト。"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from joryu.preflight import (
    DISK_REQUIRED_GB,
    PreflightError,
    changed_services_from_git,
    check_disk_space,
    path_affects_service,
    required_disk_gb,
    resolve_up_services,
    services_to_build,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/joryu/cli/up.py", {"joryu"}),
        ("src/joryu/jobs/models.py", {"api"}),
        ("src/joryu/api/app.py", {"api"}),
        ("Dockerfile.api", {"api"}),
        ("Dockerfile", {"joryu"}),
        ("pyproject.toml", {"joryu"}),
        ("dashboard/src/app/page.tsx", {"dashboard"}),
        ("dashboard/Dockerfile", {"dashboard"}),
        ("dashboard/public/.gitkeep", {"dashboard"}),
        ("dashboard/public/responses.jsonl", set()),
        ("dashboard/public/stats.json", set()),
        ("README.md", {"joryu"}),
        ("docs/architecture.md", set()),
    ],
)
def test_path_affects_service(path: str, expected: set[str]) -> None:
    assert path_affects_service(path) == expected


def test_changed_services_from_git_merges_sources() -> None:
    def _fake_git(args: list[str], **_kwargs: object) -> _GitResult:
        if args[:3] == ["git", "diff", "--name-only"] and args[-1] == "HEAD":
            return _GitResult(stdout="src/joryu/cli/up.py\n")
        if args[:3] == ["git", "diff", "--name-only"] and args[-1] == "--cached":
            return _GitResult(stdout="dashboard/package.json\n")
        if args[:2] == ["git", "ls-files"]:
            return _GitResult(stdout="dashboard/public/.gitkeep\n")
        return _GitResult(stdout="")

    changed = changed_services_from_git(Path("."), git_runner=_fake_git)
    assert changed == {"joryu", "dashboard"}


def test_resolve_up_services_default_no_changes() -> None:
    args = argparse.Namespace(full=False, frontend_only=False, backend_only=False)
    assert resolve_up_services(args, set()) == ["dashboard", "api"]


def test_resolve_up_services_default_with_joryu_diff() -> None:
    args = argparse.Namespace(full=False, frontend_only=False, backend_only=False)
    assert resolve_up_services(args, {"joryu"}) == ["dashboard", "api"]


def test_resolve_up_services_default_with_both_diffs() -> None:
    args = argparse.Namespace(full=False, frontend_only=False, backend_only=False)
    assert resolve_up_services(args, {"joryu", "dashboard"}) == ["dashboard", "api"]
    assert resolve_up_services(args, {"api", "dashboard"}) == ["dashboard", "api"]


def test_resolve_up_services_full() -> None:
    args = argparse.Namespace(full=True, frontend_only=False, backend_only=False)
    assert resolve_up_services(args, {"joryu"}) == ["dashboard", "api", "joryu"]


def test_services_to_build_intersection() -> None:
    assert services_to_build(["dashboard", "joryu"], {"joryu"}, no_build=False) == ["joryu"]
    assert services_to_build(["dashboard"], {"joryu"}, no_build=False) == []
    assert services_to_build(["dashboard"], {"dashboard"}, no_build=True) == []


def test_required_disk_gb_sums_thresholds() -> None:
    assert required_disk_gb(["dashboard"]) == DISK_REQUIRED_GB["dashboard"]
    assert required_disk_gb(["joryu"]) == DISK_REQUIRED_GB["joryu"]
    assert required_disk_gb(["dashboard", "joryu"]) == (
        DISK_REQUIRED_GB["dashboard"] + DISK_REQUIRED_GB["joryu"]
    )


def test_check_disk_space_aborts_when_insufficient() -> None:
    free_bytes = int(4 * 1024**3)  # 4 GB < 5 GB dashboard threshold
    with pytest.raises(PreflightError, match="空き容量不足"):
        check_disk_space(
            ["dashboard"],
            Path("."),
            force=False,
            disk_usage_fn=lambda _p: (100, 100, free_bytes),
        )


def test_check_disk_space_skipped_with_force() -> None:
    free_bytes = int(1 * 1024**3)
    check_disk_space(
        ["joryu"],
        Path("."),
        force=True,
        disk_usage_fn=lambda _p: (100, 100, free_bytes),
    )


class _GitResult:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
