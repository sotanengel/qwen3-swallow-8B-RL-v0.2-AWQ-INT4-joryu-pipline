"""docker compose コマンドの構築と実行 (CLI から共有)。"""

from __future__ import annotations

import subprocess
import sys


def compose_build_command(*, services: list[str]) -> list[str]:
    """`docker compose build [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose", "build"]
    cmd.extend(services)
    return cmd


def compose_up_command(
    *,
    services: list[str] | None,
    detach: bool,
    build: bool,
) -> list[str]:
    """`docker compose up [--build] [-d] [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose", "up"]
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
    if services:
        cmd.extend(services)
    return cmd


def compose_down_command(*, volumes: bool) -> list[str]:
    """`docker compose down [-v]` を構築。"""
    cmd: list[str] = ["docker", "compose", "down"]
    if volumes:
        cmd.append("-v")
    return cmd


def run(cmd: list[str]) -> int:
    """ログ出しつつ subprocess.run で実行し、返り値を返す。"""
    print(f"[joryu] {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode
