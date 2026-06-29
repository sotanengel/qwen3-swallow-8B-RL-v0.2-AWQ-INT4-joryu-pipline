"""Dockerfile / pyproject vLLM インストール契約テスト。"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_dockerfile_vllm_base_smoke_test_import() -> None:
    """ビルド時に vllm._C import を検証し runtime ImportError を fail-fast する。"""
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "import vllm._C" in dockerfile
    assert "vllm+torch OK" in dockerfile


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
