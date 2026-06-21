"""joryu-up 実行前の git 差分検出とディスク preflight。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

DISK_REQUIRED_GB: dict[str, float] = {
    "dashboard": 5.0,
    "api": 2.0,
    "joryu": 25.0,
}

_JORYU_PATHS = frozenset(
    {
        "Dockerfile",
        "Dockerfile.api",
        "pyproject.toml",
        "uv.lock",
        "config.yaml",
        "styles.yaml",
        "README.md",
        ".dockerignore",
        "docker-compose.yml",
    }
)
_JORYU_PREFIXES = ("src/", "scripts/")
_API_PREFIXES = ("src/joryu/api/", "src/joryu/jobs/")
_DASHBOARD_PREFIX = "dashboard/"
_DASHBOARD_RUNTIME_PATHS = frozenset(
    {
        "dashboard/public/responses.jsonl",
        "dashboard/public/stats.json",
    }
)

_SERVICE_ORDER = ("dashboard", "api", "joryu")
_DEFAULT_UP = ("dashboard", "api")


class PreflightError(Exception):
    """preflight 失敗 (ディスク不足など)。"""


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


def path_affects_service(path: str) -> set[str]:
    """build context 上、変更パスが影響する compose サービス名を返す。"""
    normalized = path.replace("\\", "/")
    if normalized in _DASHBOARD_RUNTIME_PATHS:
        return set()
    if normalized.startswith(_API_PREFIXES) or normalized == "Dockerfile.api":
        return {"api"}
    if normalized in _JORYU_PATHS or normalized.startswith(_JORYU_PREFIXES):
        return {"joryu"}
    if normalized.startswith(_DASHBOARD_PREFIX):
        return {"dashboard"}
    return set()


def _git_lines(repo_root: Path, args: list[str], git_runner: _GitRunner) -> list[str]:
    result = git_runner(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def changed_services_from_git(
    repo_root: Path,
    *,
    git_runner: _GitRunner | None = None,
) -> set[str]:
    """git 作業ツリー差分から rebuild が必要なサービスを返す。"""
    runner = git_runner or subprocess.run
    paths: set[str] = set()
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "HEAD"], runner))
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "--cached"], runner))
    paths.update(
        _git_lines(
            repo_root,
            ["git", "ls-files", "--others", "--exclude-standard"],
            runner,
        )
    )

    services: set[str] = set()
    for path in paths:
        services.update(path_affects_service(path))
    return services


def resolve_up_services(args: argparse.Namespace, changed: set[str]) -> list[str]:
    """CLI フラグから `docker compose up` 対象サービスを決定。

    git 差分 (`changed`) は build 対象の判定にのみ使う。既定モードでは常に
    dashboard + api を起動する。
    """
    del changed  # build 判定は services_to_build 側
    if args.full:
        return list(_SERVICE_ORDER)
    if args.backend_only:
        return ["joryu"]
    if args.frontend_only:
        return ["dashboard"]
    return list(_DEFAULT_UP)


def services_to_build(
    up_services: list[str],
    changed: set[str],
    *,
    no_build: bool,
) -> list[str]:
    """`up` 対象のうち git 差分があるサービスだけ build する。"""
    if no_build:
        return []
    return [svc for svc in up_services if svc in changed]


def required_disk_gb(services: list[str]) -> float:
    """ビルド対象サービスに必要なホスト空き容量 (GB)。"""
    return sum(DISK_REQUIRED_GB[svc] for svc in services)


def check_disk_space(
    services: list[str],
    repo_root: Path,
    *,
    force: bool,
    disk_usage_fn: Callable[[Path], tuple[int, int, int]] | None = None,
) -> None:
    """空き容量不足なら PreflightError。force=True ならスキップ。"""
    if force or not services:
        return

    usage = (disk_usage_fn or shutil.disk_usage)(repo_root)
    free_gb = usage[2] / (1024**3)
    need_gb = required_disk_gb(services)

    if free_gb >= need_gb:
        return

    service_list = ", ".join(services)
    msg = (
        f"[joryu-up] 空き容量不足: {free_gb:.1f} GB 空き / {need_gb:.0f} GB 必要 ({service_list})\n"
        "  Docker Desktop の Disk image size を確認するか、"
        "`docker system prune -af` で不要イメージを削除してください。\n"
        "  容量不足を承知で続行する場合は `--force` を付けて再実行してください。"
    )
    raise PreflightError(msg)
