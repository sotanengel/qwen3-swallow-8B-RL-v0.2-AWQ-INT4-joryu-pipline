"""Docker デリゲート: Windows → コンテナの自動委譲とコマンド構築。"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

DEFAULT_IMAGE = "joryu:latest"


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
    allocate_tty: bool = False,
    extra_args: list[str],
    cli_module: str = "joryu.cli.distill",
    native_flag: str | None = "--no-docker",
) -> list[str]:
    """`docker run --gpus all ... python -m <cli_module> --config <c> <extra>` を構築。"""
    cmd: list[str] = [
        "docker",
        "run",
        "--rm",
    ]
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
) -> int:
    cwd = Path.cwd()
    config_path = (cwd / config).resolve()
    if not config_path.exists():
        print(f"[joryu] config not found: {config_path}", file=sys.stderr)
        return 2

    from joryu.docker_runtime import prepare_distill_docker_mounts

    try:
        mounts = prepare_distill_docker_mounts(cwd, config_path, config_rel=config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[joryu] config error: {exc}", file=sys.stderr)
        return 2

    if "--style" in extra_args or any(a.startswith("--style") for a in extra_args):
        if mounts.styles_path is None:
            from joryu.config import load_config

            cfg = load_config(config_path)
            candidate = (config_path.parent / cfg.distill.styles_file).resolve()
            print(f"[joryu] styles file not found: {candidate}", file=sys.stderr)
            return 2

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
        allocate_tty=sys.stderr.isatty(),
        extra_args=extra_args,
        cli_module=cli_module,
        native_flag=native_flag,
    )
    print(f"[joryu] docker delegate: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode
