"""Docker-out-of-Docker 向けホストパス解決。

API コンテナ内の ``/workspace`` はホスト Docker デーモンからは見えない。
``docker compose run`` の volume マウントが壊れないよう、bind mount の
実パス（Docker Desktop の ``/host_mnt/...`` 等）へ変換する。
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[/\\]?(.*)$")


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _path_from_9p_mount(root_in_share: str, super_opts: str) -> str | None:
    """9p/drvfs マウント (Docker Desktop の ``.: /workspace``) からホストパスを復元。"""
    drive_base: str | None = None
    for part in super_opts.split(","):
        for kv in part.split(";"):
            if kv.startswith("path="):
                drive_base = kv[5:]
                break
        if drive_base is not None:
            break
    if not drive_base:
        return None
    rel = root_in_share.strip("/")
    base = drive_base.rstrip("\\/")
    if rel:
        return f"{base}/{rel}"
    return base


def _to_docker_daemon_path(path: str) -> str:
    """Linux コンテナ内から Docker Desktop デーモンへ渡す bind パスへ正規化。"""
    match = _DRIVE_PATH_RE.match(path)
    if match and os.name != "nt":
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/").lstrip("/")
        return f"/run/desktop/mnt/host/{drive}/{rest}"
    return path


def _parse_mountinfo_mount_source(
    mountinfo: str,
    mount_point: PurePosixPath,
) -> Path | None:
    """``/proc/self/mountinfo`` から *mount_point* の bind 元パスを返す。"""
    target = mount_point.as_posix().rstrip("/") or "/"
    best_len = -1
    best_source: str | None = None

    for line in mountinfo.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_fields = left.split()
        if len(left_fields) < 5:
            continue
        root_in_share = left_fields[3]
        mp = left_fields[4]
        mp_norm = mp.rstrip("/") or "/"
        if mp_norm != target and not target.startswith(mp_norm + "/"):
            continue
        right_fields = right.split()
        if len(right_fields) < 2:
            continue
        fs_type = right_fields[0]
        mount_source = right_fields[1]
        super_opts = right_fields[2] if len(right_fields) > 2 else ""

        candidate: str | None
        if fs_type == "9p":
            candidate = _path_from_9p_mount(root_in_share, super_opts)
        elif mount_source.startswith("/"):
            candidate = mount_source
        else:
            candidate = None

        if candidate is not None and len(mp_norm) > best_len:
            best_len = len(mp_norm)
            best_source = _to_docker_daemon_path(candidate)

    return Path(best_source) if best_source is not None else None


def resolve_host_repo_root(
    repo_root: Path,
    *,
    env: dict[str, str] | None = None,
    mountinfo_reader: Callable[[], str] | None = None,
) -> Path:
    """Docker デーモンが bind mount できるリポジトリルートを返す。"""
    e = os.environ if env is None else env
    explicit = e.get("JORYU_HOST_REPO_ROOT", "").strip()
    if explicit:
        return Path(explicit)

    container_root = e.get("JORYU_REPO_ROOT", "").strip()
    roots_to_try: list[Path] = []
    if container_root:
        roots_to_try.append(Path(container_root))
    roots_to_try.append(repo_root)

    if mountinfo_reader is not None:
        mountinfo = mountinfo_reader()
    else:
        mountinfo_path = Path("/proc/self/mountinfo")
        if not mountinfo_path.exists():
            return repo_root.resolve()
        mountinfo = mountinfo_path.read_text(encoding="utf-8")

    for root in roots_to_try:
        host = _parse_mountinfo_mount_source(mountinfo, PurePosixPath(root.as_posix()))
        if host is not None:
            return host

    return repo_root.resolve()


def map_path_for_docker(
    path: Path,
    *,
    repo_root: Path,
    host_repo_root: Path | None = None,
    env: dict[str, str] | None = None,
    mountinfo_reader: Callable[[], str] | None = None,
) -> Path:
    """コンテナ内パスを Docker デーモン向けホストパスへ変換する。"""
    host_root = host_repo_root or resolve_host_repo_root(
        repo_root,
        env=env,
        mountinfo_reader=mountinfo_reader,
    )
    container_root = (env or os.environ).get("JORYU_REPO_ROOT", "").strip()
    bases: list[Path] = []
    if container_root:
        bases.append(Path(container_root))
    bases.append(repo_root)

    resolved = path.resolve()
    for base in bases:
        if _is_under(resolved, base):
            rel = resolved.relative_to(base.resolve())
            host_base = str(host_root).replace("\\", "/").rstrip("/")
            return Path(f"{host_base}/{rel.as_posix()}")
    return resolved
