"""Dockerfile / pyproject vLLM インストール契約テスト。"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_app_stage_from_vllm_base() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM joryu-vllm-base:latest" in dockerfile
    assert "git+https://github.com/vllm-project/vllm" not in dockerfile
    assert "vllm==0.23.0" not in dockerfile
    assert "uv pip install" not in dockerfile


def test_dockerfile_vllm_base_has_torch_and_git_vllm() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile.vllm-base").read_text(encoding="utf-8")
    assert "git+https://github.com/vllm-project/vllm@v0.23.1rc0" in dockerfile
    assert "torch>=" in dockerfile
    assert "MAX_JOBS=1" in dockerfile
    assert "UV_TORCH_BACKEND=cu130" in dockerfile
    assert "id=joryu-uv-cu130,sharing=locked" in dockerfile
    assert dockerfile.count("uv pip install") >= 2


def test_dockerfile_app_syncs_on_top_of_base_venv() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --extra api" in dockerfile
    assert "COPY --from=builder /app/src /app/src" in dockerfile


def test_pyproject_no_git_vllm_source() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.uv.sources]" not in text or "vllm = { git" not in text
    assert 'vllm = ["vllm==0.23.0"]' in text or "vllm==0.23.0" in text
