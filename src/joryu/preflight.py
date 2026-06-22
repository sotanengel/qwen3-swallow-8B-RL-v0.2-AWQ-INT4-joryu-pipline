"""joryu-up 実行前の git 差分検出とディスク preflight。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

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
    }
)
_JORYU_PREFIXES = ("src/", "scripts/")
_API_PREFIXES = ("src/joryu/api/", "src/joryu/jobs/")
# API ジョブ実行時に joryu コンテナへも載るモジュール (api + joryu 両方 rebuild)
_JORYU_JOB_RUNTIME_PATHS = frozenset(
    {
        "docker-compose.yml",
        "src/joryu/distill.py",
        "src/joryu/docker_delegate.py",
        "src/joryu/docker_runtime.py",
        "src/joryu/stats.py",
        "src/joryu/cli/distill.py",
        "src/joryu/cli/stats.py",
    }
)
_DASHBOARD_PREFIX = "dashboard/"
_DASHBOARD_RUNTIME_PATHS = frozenset(
    {
        "dashboard/public/responses.jsonl",
        "dashboard/public/stats.json",
    }
)

_SERVICE_ORDER = ("dashboard", "api", "joryu")
_DEFAULT_UP = ("dashboard", "api")
_UP_STATE_REL = Path("data") / ".joryu" / "up-state.json"


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


class _InspectRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


JORYU_JOB_IMAGE = "joryu:latest"


def docker_image_exists(
    image: str,
    *,
    inspect_runner: _InspectRunner | None = None,
) -> bool:
    """ローカルに Docker イメージが存在するか。"""
    runner = inspect_runner or subprocess.run
    result = runner(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def path_affects_service(path: str) -> set[str]:
    """build context 上、変更パスが影響する compose サービス名を返す。"""
    normalized = path.replace("\\", "/")
    if normalized in _DASHBOARD_RUNTIME_PATHS:
        return set()
    if normalized.startswith(_API_PREFIXES) or normalized == "Dockerfile.api":
        return {"api"}
    if normalized in _JORYU_JOB_RUNTIME_PATHS:
        return {"api", "joryu"}
    if normalized.startswith(_DASHBOARD_PREFIX):
        return {"dashboard"}
    if normalized in _JORYU_PATHS or normalized.startswith(_JORYU_PREFIXES):
        return {"joryu"}
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


def up_state_path(repo_root: Path) -> Path:
    return repo_root / _UP_STATE_REL


def load_up_state(repo_root: Path) -> dict[str, Any] | None:
    path = up_state_path(repo_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and isinstance(data.get("git_head"), str):
        return data
    return None


def save_up_state(repo_root: Path, git_head: str) -> None:
    path = up_state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"git_head": git_head}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def git_head_at(repo_root: Path, *, git_runner: _GitRunner | None = None) -> str | None:
    runner = git_runner or subprocess.run
    lines = _git_lines(repo_root, ["git", "rev-parse", "HEAD"], runner)
    return lines[0] if lines else None


def _paths_from_working_tree(repo_root: Path, git_runner: _GitRunner) -> set[str]:
    paths: set[str] = set()
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "HEAD"], git_runner))
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "--cached"], git_runner))
    paths.update(
        _git_lines(
            repo_root,
            ["git", "ls-files", "--others", "--exclude-standard"],
            git_runner,
        )
    )
    return paths


def _paths_since_last_up(
    repo_root: Path,
    *,
    git_runner: _GitRunner,
    state: dict[str, Any] | None,
    head: str | None,
) -> set[str]:
    if not state or not head:
        return set()
    last_head = state["git_head"]
    if last_head == head:
        return set()
    return set(
        _git_lines(
            repo_root,
            ["git", "diff", "--name-only", f"{last_head}..{head}"],
            git_runner,
        )
    )


def changed_services_from_git(
    repo_root: Path,
    *,
    git_runner: _GitRunner | None = None,
) -> set[str]:
    """rebuild が必要なサービスを返す。

    未コミットの作業ツリー差分に加え、前回 ``joryu-up`` 成功時の HEAD から
    現在の HEAD までに入ったコミット（``git pull`` 後など）も対象にする。
    """
    runner = git_runner or subprocess.run
    head = git_head_at(repo_root, git_runner=runner)
    state = load_up_state(repo_root)
    paths = _paths_from_working_tree(repo_root, runner)
    paths.update(_paths_since_last_up(repo_root, git_runner=runner, state=state, head=head))

    services: set[str] = set()
    for path in paths:
        services.update(path_affects_service(path))
    return services


def is_first_up_run(repo_root: Path) -> bool:
    """前回成功した joryu-up の記録が無い。"""
    return load_up_state(repo_root) is None


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
    force_build: bool = False,
    first_run: bool = False,
    inspect_runner: _InspectRunner | None = None,
) -> list[str]:
    """`up` 対象のうち rebuild が必要なサービスだけ build する。"""
    if no_build:
        return []
    if force_build:
        candidates = list(up_services)
    elif first_run:
        candidates = list(up_services)
    else:
        candidates = [svc for svc in up_services if svc in changed]

    # api を up する = ジョブが joryu:latest を docker run する。
    if "api" in up_services and "joryu" not in candidates:
        needs_joryu = (
            "joryu" in changed
            or first_run
            or force_build
            or not docker_image_exists(JORYU_JOB_IMAGE, inspect_runner=inspect_runner)
        )
        if needs_joryu:
            candidates.append("joryu")

    return [svc for svc in _SERVICE_ORDER if svc in candidates]


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


def ensure_dashboard_data_paths(repo_root: Path) -> None:
    """蒸留 JSONL を dashboard から参照できるようディレクトリと symlink を整備する。"""
    from joryu.paths import DEFAULT_CONFIG, dashboard_public, resolve_optional_config

    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)

    distilled_dir = repo_root / cfg.distill.out_dir
    distilled_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = distilled_dir / cfg.distill.out_file
    if not jsonl_path.exists():
        jsonl_path.touch()

    public_dir = dashboard_public(repo_root)
    public_jsonl = public_dir / cfg.distill.out_file

    if public_jsonl.exists() or public_jsonl.is_symlink():
        return

    try:
        public_jsonl.symlink_to(jsonl_path.resolve(), target_is_directory=False)
    except OSError:
        try:
            rel = Path(os.path.relpath(jsonl_path.resolve(), public_dir))
            public_jsonl.symlink_to(rel, target_is_directory=False)
        except OSError:
            pass
