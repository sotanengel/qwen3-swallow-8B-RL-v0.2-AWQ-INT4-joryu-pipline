"""git プランビングの薄いラッパー (HEAD 解決に使う)。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class _GitRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


def _git_lines(repo_root: Path, args: list[str], git_runner: _GitRunner) -> list[str]:
    try:
        result = git_runner(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_head_at(repo_root: Path, *, git_runner: _GitRunner | None = None) -> str | None:
    runner = git_runner or subprocess.run
    lines = _git_lines(repo_root, ["git", "rev-parse", "HEAD"], runner)
    return lines[0] if lines else None
