"""Dockerfile / pyproject vLLM インストール契約テスト。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TORCH_STACK_SCRIPT = REPO_ROOT / "scripts" / "vllm_base_torch_stack.py"


def _load_torch_stack():
    spec = importlib.util.spec_from_file_location("vllm_base_torch_stack", TORCH_STACK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vllm_base_dockerfile() -> str:
    return (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")


def _dockerfile_stage(dockerfile: str, stage: str) -> str:
    marker = f"AS {stage}"
    start = dockerfile.index(marker)
    from_start = dockerfile.rfind("FROM", 0, start)
    next_from = dockerfile.find("\nFROM ", start + len(marker))
    if next_from == -1:
        return dockerfile[from_start:]
    return dockerfile[from_start:next_from]


def test_dockerfile_vllm_base_no_joryu_app_layer() -> None:
    """base は vLLM runtime のみ。joryu アプリ層は joryu-job に委譲する。"""
    dockerfile = _vllm_base_dockerfile()
    assert "COPY src" not in dockerfile
    assert "--extra api" not in dockerfile
    assert "PYTHONPATH=/app/src" not in dockerfile
    assert "uv sync" not in dockerfile


def test_dockerfile_vllm_base_multistage_compile_runtime() -> None:
    """compile で vLLM をビルドし runtime に venv のみ渡すマルチステージ契約。"""
    dockerfile = _vllm_base_dockerfile()
    assert "AS compile" in dockerfile
    assert "AS runtime" in dockerfile
    assert "COPY --from=compile /app/.venv /app/.venv" in dockerfile


def test_dockerfile_vllm_base_runtime_no_build_toolchain() -> None:
    """runtime stage に build-essential / ccache を入れない。"""
    runtime = _dockerfile_stage(_vllm_base_dockerfile(), "runtime")
    assert "build-essential" not in runtime
    assert "ccache" not in runtime
    compile = _dockerfile_stage(_vllm_base_dockerfile(), "compile")
    assert "build-essential" in compile
    assert "ccache" in compile


def test_dockerfile_app_stage_from_vllm_base() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile.job").read_text(encoding="utf-8")
    assert "FROM joryu-vllm-base:latest" in dockerfile
    assert "git+https://github.com/vllm-project/vllm" not in dockerfile
    assert "vllm==0.23.0" not in dockerfile
    assert "uv pip install" not in dockerfile


def test_dockerfile_vllm_base_has_torch_and_git_vllm() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "git+https://github.com/vllm-project/vllm@v0.23.1rc0" in dockerfile
    assert "torch==2.12.1+cu130" in dockerfile
    assert "UV_TORCH_BACKEND=cu130" in dockerfile
    assert "id=joryu-uv-cu130,sharing=locked" in dockerfile
    assert dockerfile.count("uv pip install") >= 2


def test_dockerfile_vllm_base_forces_source_build() -> None:
    """stale uv wheel / precompiled 経路で torch ABI mismatch になるのを防ぐ契約 (#342)。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "VLLM_USE_PRECOMPILED=0" in dockerfile
    assert "--no-build-isolation" in dockerfile
    assert "--reinstall-package vllm" in dockerfile


def test_dockerfile_vllm_base_vllm_install_no_uv_cache_mount() -> None:
    """vLLM install step は uv cache mount を使わず stale wheel 再利用を防ぐ。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    marker = "--reinstall-package vllm"
    start = dockerfile.index(marker)
    vllm_run = dockerfile.rfind("RUN", 0, start)
    vllm_block = dockerfile[vllm_run : dockerfile.find("\n\n", start)]
    assert "joryu-uv-cu130" not in vllm_block
    assert "joryu-ccache" in vllm_block


def test_dockerfile_vllm_base_uses_smoke_script() -> None:
    """ビルド時 smoke は scripts/vllm_base_smoke.py で vllm serve 経路を検証する。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "COPY scripts/vllm_base_smoke.py scripts/vllm_base_smoke.py" in dockerfile
    assert "RUN python scripts/vllm_base_smoke.py" in dockerfile


def test_vllm_base_torch_stack_ssot_matches_dockerfile() -> None:
    """SSOT と Dockerfile の torch/torchvision/torchaudio pin が一致する。"""
    stack = _load_torch_stack()
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    for pkg, version in stack.TORCH_STACK.items():
        assert f"{pkg}=={version}" in dockerfile
    assert stack.PYTORCH_INDEX in dockerfile


def test_dockerfile_vllm_base_realigns_torch_stack_after_vllm() -> None:
    """vLLM install 後に torchvision 等が transitive で戻るのを防ぐ realign 契約。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    vllm_idx = dockerfile.index("--reinstall-package vllm")
    after_vllm = dockerfile[vllm_idx:]
    assert "--reinstall-package torchvision" in after_vllm
    assert "--reinstall-package torchaudio" in after_vllm
    assert "--reinstall-package torch" in after_vllm


def test_dockerfile_vllm_base_installs_build_deps_for_no_build_isolation() -> None:
    """--no-build-isolation では vLLM build-system requires を venv に入れてからビルドする。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "setuptools-rust>=1.9.0" in dockerfile
    assert "cmake>=3.26.1" in dockerfile
    build_deps_idx = dockerfile.index("setuptools-rust>=1.9.0")
    vllm_idx = dockerfile.index("--reinstall-package vllm")
    assert build_deps_idx < vllm_idx


def test_dockerfile_vllm_base_parallel_build_settings() -> None:
    """`MAX_JOBS=1` だと nvcc 直列で実用不能 (試行 1 で 2 時間 hang を確認)。

    12 論理 CPU の半分以下を上限に nvcc を並列化し、CUDA arch も実機向けに
    絞ることでビルド時間を 1/24〜1/32 に短縮する契約。
    """
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "MAX_JOBS=4" in dockerfile
    assert "NVCC_THREADS=2" in dockerfile
    assert 'TORCH_CUDA_ARCH_LIST="8.6"' in dockerfile


def test_dockerfile_vllm_base_uses_ccache() -> None:
    """ccache 同梱で再ビルド時の CUDA カーネル再コンパイルを抑える。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "ccache" in dockerfile
    assert "id=joryu-ccache" in dockerfile
    assert "CCACHE_DIR=/root/.cache/ccache" in dockerfile


def test_dockerfile_vllm_base_verbose_pip_install() -> None:
    """vLLM の uv pip install を `-v` 化し setup.py の進捗を出させる。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "uv pip install -v --no-build-isolation --reinstall-package vllm" in dockerfile
    assert '"vllm @ git+' in dockerfile


def test_dockerfile_app_syncs_on_top_of_base_venv() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile.job").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --extra api" in dockerfile
    assert "COPY --from=builder /app/src /app/src" in dockerfile


def test_pyproject_no_git_vllm_source() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.uv.sources]" not in text or "vllm = { git" not in text
    assert 'vllm = ["vllm==0.23.0"]' in text or "vllm==0.23.0" in text
