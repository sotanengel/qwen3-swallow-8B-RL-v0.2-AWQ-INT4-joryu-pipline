"""docker compose コマンドの構築と実行 (CLI から共有)。"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

VLLM_BASE_DOCKERFILE = "Dockerfile.vllm-base"
JORYU_VLLM_BASE_IMAGE = "joryu-vllm-base:latest"


def vllm_base_build_command(*, repo_root: str) -> list[str]:
    """``docker build --progress=plain -f Dockerfile.vllm-base -t joryu-vllm-base:latest`` を構築。

    ``--progress=plain`` を**必ず**付ける。試行 1 (PR #329 の初版) では既定の
    ``--progress=auto`` で setup.py の出力が完全に隠れ、ビルドが hang か進行中か
    判別不能となった。joryu-up からの自動ビルドでも同じ理由で plain 化する。
    """
    return [
        "docker",
        "build",
        "--progress=plain",
        "-f",
        VLLM_BASE_DOCKERFILE,
        "-t",
        JORYU_VLLM_BASE_IMAGE,
        repo_root,
    ]


def compose_build_command(
    *,
    services: list[str],
    profiles: list[str] | None = None,
) -> list[str]:
    """`docker compose build [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose"]
    if profiles:
        for profile in profiles:
            cmd.extend(["--profile", profile])
    cmd.append("build")
    cmd.extend(services)
    return cmd


def staged_build_commands(
    services: list[str],
    *,
    profiles: list[str] | None = None,
) -> list[list[str]]:
    """joryu GPU イメージを先に単独 build し、残りを並列 build する。

    並列 build 時の CPU 競合 (api/dashboard uv sync タイムアウト) を避ける。
    """
    if not services:
        return []
    # joryu / joryu-seed は image: 直参照になり build 対象外。joryu-job (新ジョブ image)
    # と joryu-judge を heavy として単独 build する。
    heavy = [s for s in services if s in ("joryu-job", "joryu-judge")]
    light = [s for s in services if s not in heavy]
    cmds: list[list[str]] = []
    for svc in heavy:
        cmds.append(compose_build_command(services=[svc], profiles=profiles))
    if light:
        cmds.append(compose_build_command(services=light, profiles=profiles))
    return cmds


def compose_up_command(
    *,
    services: list[str] | None,
    detach: bool,
    build: bool,
    force_recreate: bool = False,
    profiles: list[str] | None = None,
) -> list[str]:
    """`docker compose up [--build] [--force-recreate] [-d] [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose"]
    if profiles:
        for profile in profiles:
            cmd.extend(["--profile", profile])
    cmd.append("up")
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


def compose_stop_command(*, services: list[str]) -> list[str]:
    """`docker compose stop [services...]` を構築。"""
    cmd: list[str] = ["docker", "compose", "stop"]
    cmd.extend(services)
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
    """build 後: dangling image と旧 build cache を回収する。"""
    for cmd in build_artifact_cleanup_commands():
        run(cmd)


def run_up_startup_cleanup() -> None:
    """joryu-up 開始直後: dangling (<none>) image を回収する。"""
    run(image_prune_command())


def run_pre_browser_image_cleanup() -> None:
    """build 完了後・ブラウザ起動直前: dangling (<none>) image を回収する。"""
    logger.info(
        "[joryu-up] removing dangling images (<none>) before opening browser",
    )
    run(image_prune_command())


def run_builder_cache_cleanup() -> None:
    """disk 不足リトライ時: 未参照 build cache のみ回収 (image prune は起動時済み)。"""
    run(builder_prune_command())


def run(cmd: list[str]) -> int:
    """ログ出しつつ subprocess.run で実行し、返り値を返す。"""
    logger.info("[joryu] %s", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode
