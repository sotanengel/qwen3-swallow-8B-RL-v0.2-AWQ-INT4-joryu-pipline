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
    """`docker builder prune -af`。現行 image から参照されない全 cache を回収する。

    `-f` だけだと dangling (完全に孤立した) cache layer しか削除されず、
    旧世代の reusable cache が世代毎に 10-20 GB ずつ積み増しされる
    (実機で 40 GB に育つ事象を確認)。
    `-a` も付けると「current image 群から参照されていない全 cache」を
    削除でき、世代を跨いだ累積を断ち切れる。

    build 直後に呼ぶ前提なので、現行 `joryu:latest` 等の参照層は残り、
    次回の incremental build は通常通り cache hit する。
    """
    return ["docker", "builder", "prune", "-a", "-f"]


def image_prune_command() -> list[str]:
    """`docker image prune -f`。タグなし (dangling) イメージのみ削除する。

    タグ付きで稼働中の `joryu:latest` などは影響を受けない。
    disk preflight が落ちた時の自動 reclaim 用。
    """
    return ["docker", "image", "prune", "-f"]


def build_artifact_cleanup_commands() -> list[list[str]]:
    """build 後 cleanup: dangling image と旧 build cache を順に回収する。"""
    return [image_prune_command(), builder_prune_command()]


def run_build_artifact_cleanup() -> None:
    """build 後 / disk preflight リトライ時の cleanup を実行する。"""
    for cmd in build_artifact_cleanup_commands():
        run(cmd)


def run(cmd: list[str]) -> int:
    """ログ出しつつ subprocess.run で実行し、返り値を返す。"""
    print(f"[joryu] {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode
