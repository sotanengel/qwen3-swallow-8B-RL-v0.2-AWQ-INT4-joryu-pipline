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
    hf_cache: Path,
    extra_args: list[str],
) -> list[str]:
    """`docker run --gpus all ... joryu-distill --no-docker --config <c> <extra>` を構築。"""
    return [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "-v",
        f"{data_dir}:/app/data",
        "-v",
        f"{config_path}:/app/{config_rel}:ro",
        "-v",
        f"{src_dir}:/app/src:ro",
        "-v",
        f"{hf_cache}:/root/.cache/huggingface",
        "-e",
        "HF_HOME=/root/.cache/huggingface",
        "-e",
        "PYTHONPATH=/app/src",
        "-e",
        "VLLM_USE_FLASHINFER_SAMPLER=0",
        "-e",
        "VLLM_ATTENTION_BACKEND=FLASH_ATTN",
        image,
        "python",
        "-m",
        "joryu.cli.distill",
        "--no-docker",
        "--config",
        config_rel,
        *extra_args,
    ]


def run_in_docker(
    *,
    image: str = DEFAULT_IMAGE,
    config: str,
    extra_args: list[str],
) -> int:
    cwd = Path.cwd()
    config_path = (cwd / config).resolve()
    if not config_path.exists():
        print(f"[joryu] config not found: {config_path}", file=sys.stderr)
        return 2
    data_dir = cwd / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    hf_cache = hf_cache_dir()
    hf_cache.mkdir(parents=True, exist_ok=True)
    src_dir = (cwd / "src").resolve()

    cmd = build_docker_command(
        image=image,
        cwd=cwd,
        config_path=config_path,
        config_rel=config,
        src_dir=src_dir,
        data_dir=data_dir,
        hf_cache=hf_cache,
        extra_args=extra_args,
    )
    print(f"[joryu] docker delegate: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode
