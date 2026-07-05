"""infra/git.py: git_head_at の git プランビング処理のユニットテスト。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from joryu.infra.git import git_head_at


def _fake_git_runner(stdout: str, *, returncode: int = 0):
    def _runner(
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    return _runner


def test_git_head_at_returns_first_line(tmp_path: Path) -> None:
    runner = _fake_git_runner("abc123deadbeef\n")
    assert git_head_at(tmp_path, git_runner=runner) == "abc123deadbeef"


def test_git_head_at_returns_none_when_command_fails(tmp_path: Path) -> None:
    runner = _fake_git_runner("", returncode=1)
    assert git_head_at(tmp_path, git_runner=runner) is None


def test_git_head_at_returns_none_when_output_blank(tmp_path: Path) -> None:
    runner = _fake_git_runner("\n")
    assert git_head_at(tmp_path, git_runner=runner) is None


def test_git_head_at_returns_none_when_git_executable_missing(tmp_path: Path) -> None:
    def _missing_git_runner(
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", "git")

    assert git_head_at(tmp_path, git_runner=_missing_git_runner) is None


def test_git_head_at_uses_real_subprocess_by_default(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "x",
        ],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    head = git_head_at(tmp_path)
    assert head is not None
    assert len(head) == 40
