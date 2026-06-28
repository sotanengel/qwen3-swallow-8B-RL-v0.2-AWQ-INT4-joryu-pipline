"""Dockerfile / pyproject vLLM インストール契約テスト。"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_pinned_vllm_wheel_not_git_source() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "git+https://github.com/vllm-project/vllm" not in dockerfile
    assert "vllm==0.23.0" in dockerfile
    assert "UV_TORCH_BACKEND=cu130" in dockerfile


def test_dockerfile_torch_and_vllm_separate_run_layers() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("uv pip install") >= 2
    torch_idx = dockerfile.index("torch>=")
    vllm_idx = dockerfile.index("vllm==0.23.0")
    assert torch_idx < vllm_idx


def test_pyproject_no_git_vllm_source() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.uv.sources]" not in text or "vllm = { git" not in text
    assert 'vllm = ["vllm==0.23.0"]' in text or "vllm==0.23.0" in text
