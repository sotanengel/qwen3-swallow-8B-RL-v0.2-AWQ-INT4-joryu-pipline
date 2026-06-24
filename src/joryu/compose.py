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
    force_recreate: bool = False,
) -> list[str]:
    """`docker compose up [--build] [--force-recreate] [-d] [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose", "up"]
    if build:
        cmd.append("--build")
    if force_recreate:
        cmd.append("--force-recreate")
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


def builder_prune_command() -> list[str]:
    """`docker builder prune -f`。タグ付きイメージから参照されない層のみ削除する。

    `joryu-up` の build 直後に呼ぶことで、世代毎に発生する 16GB 規模の
    中間 vLLM ビルドキャッシュがディスクに溜まり続けるのを防ぐ。
    タグ付きイメージ (joryu:latest など) の層は参照中なので残る。
    """
    return ["docker", "builder", "prune", "-f"]


def image_prune_command() -> list[str]:
    """`docker image prune -f`。タグなし (dangling) イメージのみ削除する。

    タグ付きで稼働中の `joryu:latest` などは影響を受けない。
    disk preflight が落ちた時の自動 reclaim 用。
    """
    return ["docker", "image", "prune", "-f"]


def run(cmd: list[str]) -> int:
    """ログ出しつつ subprocess.run で実行し、返り値を返す。"""
    print(f"[joryu] {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode
