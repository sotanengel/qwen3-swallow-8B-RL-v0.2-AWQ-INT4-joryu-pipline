"""Docker デリゲート: Windows → コンテナの自動委譲とコマンド構築。"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ジョブ実行用 image (api コンテナが `docker compose run --rm joryu-job ...` で起動)。
# 常駐 vLLM サーバ (joryu / joryu-seed) は `joryu-vllm-base:latest` を直接参照する。
DEFAULT_IMAGE = "joryu-job:latest"
JORYU_PROBE_CONTAINER = "joryu-probe-vllm"
JORYU_DISTILL_HOST_CONTAINER = "joryu-distill-host"
JORYU_COMPOSE_CONTAINER_NAMES = frozenset(
    {
        "joryu",
        "joryu-seed",
        "joryu-judge",
        "joryu-job",
        "joryu-dashboard",
        "joryu-mcp",
        "joryu-api",
    }
)
JORYU_MANAGED_PREFIXES = ("joryu-job-", "joryu-probe-", "joryu-distill-")

logger = logging.getLogger(__name__)


def is_managed_joryu_container(name: str) -> bool:
    """compose 常駐・ジョブ・名前付き一時コンテナなら True (Docker 自動命名は False)。"""
    if name in JORYU_COMPOSE_CONTAINER_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in JORYU_MANAGED_PREFIXES)


def stop_docker_container(
    name: str,
    *,
    grace_seconds: int = 10,
    kill_timeout_seconds: int = 15,
    rm_timeout_seconds: int = 15,
    docker_run: Callable[..., Any] | None = None,
) -> bool:
    """同名コンテナが残っていれば停止 (再 run 前の GPU 占有防止)。

    on-failure restart による自動再起動を防ぐため、停止前に restart を無効化する。
    grace 秒以内に docker stop し、まだ running なら docker kill、それでも残れば rm -f。
    停止できた (または元から停止) なら True。
    """
    runner = docker_run or subprocess.run
    if not _container_exists(name, docker_run=runner):
        return True
    if _container_running(name, docker_run=runner):
        _disable_container_restart(name, docker_run=runner)

    if not _container_running(name, docker_run=runner):
        return True

    stop_timeout = grace_seconds + kill_timeout_seconds
    try:
        runner(
            ["docker", "stop", "--time", str(grace_seconds), name],
            capture_output=True,
            text=True,
            check=False,
            timeout=stop_timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("docker stop timed out for %s after %ss", name, stop_timeout)

    if _container_running(name, docker_run=runner):
        try:
            runner(
                ["docker", "kill", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=kill_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning("docker kill timed out for %s", name)

    if _container_running(name, docker_run=runner):
        try:
            runner(
                ["docker", "rm", "-f", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=rm_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning("docker rm timed out for %s", name)
            return False

    return not _container_running(name, docker_run=runner)


def _container_exists(name: str, *, docker_run: Callable[..., Any]) -> bool:
    try:
        proc = docker_run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0


def _disable_container_restart(name: str, *, docker_run: Callable[..., Any]) -> None:
    try:
        docker_run(
            ["docker", "update", "--restart=no", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("docker update --restart=no failed for %s", name, exc_info=True)


def _container_running(name: str, *, docker_run: Callable[..., Any]) -> bool:
    try:
        proc = docker_run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def is_docker_container_running(name: str, *, docker_run: Callable[..., Any] | None = None) -> bool:
    """名前付きコンテナが存在し Running か。"""
    runner = docker_run or subprocess.run
    return _container_exists(name, docker_run=runner) and _container_running(
        name, docker_run=runner
    )


def remove_foreign_project_joryu_containers(
    *,
    project_name: str = "joryu",
    docker_run: Callable[..., Any] | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    """別 compose プロジェクトのラベルを持つ joryu-* 固定名コンテナを削除する。

    以前は docker-compose.yml にトップレベル `name:` がなく、ホスト起動と API
    コンテナからの起動で compose プロジェクト名が異なった (cwd 由来)。同じ
    `container_name:` を別プロジェクトが作成した結果、Docker のグローバル
    名前空間で衝突する。`name: joryu` 導入後の初回 up でこの掃除を行う。

    compose ラベルがないコンテナ (ユーザーが手動 `docker run --name` で作った
    もの) は触らない。
    """
    runner = docker_run or subprocess.run
    for name in JORYU_COMPOSE_CONTAINER_NAMES:
        try:
            proc = runner(
                [
                    "docker",
                    "inspect",
                    "-f",
                    '{{index .Config.Labels "com.docker.compose.project"}}',
                    name,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if proc.returncode != 0:
            continue
        current = proc.stdout.strip()
        if current == project_name or not current:
            continue
        if log is not None:
            log(f"[joryu-up] removing foreign-project container {name} (project={current})")
        try:
            runner(
                ["docker", "rm", "-f", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("docker rm -f failed for foreign container %s", name, exc_info=True)


def stop_orphan_joryu_containers(
    *,
    image: str = DEFAULT_IMAGE,
    docker_run: Callable[..., Any] | None = None,
) -> None:
    """Docker 自動命名 (intelligent_jemison 等) の joryu-job:latest 一時コンテナを停止。"""
    runner = docker_run or subprocess.run
    try:
        proc = runner(
            ["docker", "ps", "-q", "--filter", f"ancestor={image}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if proc.returncode != 0:
        return
    for container_id in filter(None, proc.stdout.strip().splitlines()):
        try:
            insp = runner(
                ["docker", "inspect", "-f", "{{.Name}}", container_id],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if insp.returncode != 0:
            continue
        name = insp.stdout.strip().removeprefix("/")
        if is_managed_joryu_container(name):
            continue
        runner(
            ["docker", "stop", "--time", "10", container_id],
            capture_output=False,
            text=True,
            check=False,
        )


def should_use_docker(
    *,
    force_docker: bool,
    force_native: bool,
    system: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Docker デリゲートを使うか判定する。

    - `--docker` 指定: 常に Docker
    - `--no-docker` 指定: 常にネイティブ
    - `JORYU_NO_DOCKER` 環境変数: ネイティブ
    - それ以外: Windows のときだけ Docker (vLLM が Linux/CUDA 専用のため)
    """
    if force_docker:
        return True
    if force_native:
        return False
    e = os.environ if env is None else env
    if e.get("JORYU_NO_DOCKER"):
        return False
    sys_name = platform.system() if system is None else system
    return sys_name == "Windows"


def hf_cache_dir() -> Path:
    if hf_home := os.environ.get("HF_HOME"):
        return Path(hf_home)
    return Path.home() / ".cache" / "huggingface"


def build_docker_command(
    *,
    image: str,
    cwd: Path,
    config_path: Path,
    config_rel: str,
    src_dir: Path,
    data_dir: Path,
    hf_cache: Path | str,
    dashboard_public_dir: Path | None = None,
    styles_path: Path | None = None,
    styles_rel: str | None = None,
    tools_path: Path | None = None,
    tools_rel: str | None = None,
    allocate_tty: bool = False,
    extra_args: list[str],
    cli_module: str = "joryu.cli.distill",
    native_flag: str | None = "--no-docker",
    container_name: str | None = None,
) -> list[str]:
    """`docker run --gpus all ... python -m <cli_module> --config <c> <extra>` を構築。"""
    cmd: list[str] = [
        "docker",
        "run",
        "--rm",
    ]
    if container_name:
        cmd.extend(["--name", container_name])
    if allocate_tty:
        cmd.append("-t")
    cmd.extend(
        [
            "--gpus",
            "all",
            "-v",
            f"{data_dir}:/app/data",
            "-v",
            f"{config_path}:/app/{config_rel.replace('\\', '/')}:ro",
            "-v",
            f"{src_dir}:/app/src:ro",
            "-v",
            f"{hf_cache}:/root/.cache/huggingface",
        ]
    )
    if dashboard_public_dir is not None:
        dashboard_public_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["-v", f"{dashboard_public_dir}:/app/dashboard/public"])
    if styles_path is not None and styles_rel:
        rel = styles_rel.replace("\\", "/")
        cmd.extend(["-v", f"{styles_path}:/app/{rel}:ro"])
    if tools_path is not None and tools_rel:
        rel = tools_rel.replace("\\", "/")
        cmd.extend(["-v", f"{tools_path}:/app/{rel}:ro"])
    module_argv: list[str] = ["python", "-m", cli_module]
    if native_flag:
        module_argv.append(native_flag)
    module_argv.extend(["--config", config_rel.replace("\\", "/"), *extra_args])
    cmd.extend(
        [
            "-e",
            "HF_HOME=/root/.cache/huggingface",
            "-e",
            "PYTHONPATH=/app/src",
            "-e",
            "JORYU_REPO_ROOT=/app",
            "-e",
            "VLLM_USE_FLASHINFER_SAMPLER=0",
            "-e",
            "VLLM_ATTENTION_BACKEND=FLASH_ATTN",
            image,
            *module_argv,
        ]
    )
    return cmd


def run_in_docker(
    *,
    image: str = DEFAULT_IMAGE,
    config: str,
    extra_args: list[str],
    cli_module: str = "joryu.cli.distill",
    native_flag: str | None = "--no-docker",
    container_name: str | None = None,
) -> int:
    cwd = Path.cwd()
    config_path = (cwd / config).resolve()
    if not config_path.exists():
        logger.error("[joryu] config not found: %s", config_path)
        return 2

    from joryu.docker_runtime import prepare_distill_docker_mounts

    try:
        mounts = prepare_distill_docker_mounts(cwd, config_path, config_rel=config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("[joryu] config error: %s", exc)
        return 2

    if "--style" in extra_args or any(a.startswith("--style") for a in extra_args):
        if mounts.styles_path is None:
            from joryu.config import load_config

            cfg = load_config(config_path)
            candidate = (config_path.parent / cfg.distill.styles_file).resolve()
            logger.error("[joryu] styles file not found: %s", candidate)
            return 2

    if container_name:
        stop_docker_container(container_name)

    cmd = build_docker_command(
        image=image,
        cwd=cwd,
        config_path=mounts.config_path,
        config_rel=mounts.config_rel,
        src_dir=mounts.src_dir,
        data_dir=mounts.data_dir,
        dashboard_public_dir=mounts.dashboard_public,
        hf_cache=mounts.hf_cache,
        styles_path=mounts.styles_path,
        styles_rel=mounts.styles_rel,
        tools_path=mounts.tools_path,
        tools_rel=mounts.tools_rel,
        allocate_tty=sys.stderr.isatty(),
        extra_args=extra_args,
        cli_module=cli_module,
        native_flag=native_flag,
        container_name=container_name,
    )
    logger.info("[joryu] docker delegate: %s", " ".join(cmd))
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.stderr:
        logger.warning("%s", proc.stderr.rstrip("\n"))
    return proc.returncode
