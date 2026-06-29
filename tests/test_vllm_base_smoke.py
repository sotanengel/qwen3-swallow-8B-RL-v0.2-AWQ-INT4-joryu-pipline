"""vllm_base_smoke.py / torch stack SSOT の契約テスト。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "vllm_base_smoke.py"
TORCH_STACK_SCRIPT = REPO_ROOT / "scripts" / "vllm_base_torch_stack.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vllm_base_smoke_imports_vllm_serve_path() -> None:
    """vllm serve 起動時の transformers/torchvision 経路を smoke が通る契約。"""
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "import vllm.entrypoints.cli.main" in text
    assert "from transformers.image_utils import load_image" in text
    assert "import torchvision" in text
    assert "import vllm._C" in text


def test_vllm_base_smoke_asserts_torch_stack_versions() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert 'torch.__version__.startswith("2.12.1")' in text
    assert 'torchvision.__version__.startswith("0.27.")' in text
    assert "vllm-base smoke OK" in text


def test_torch_stack_ssot_matches_pytorch_212_train() -> None:
    """torch 2.12.1 は torchvision 0.27.x train (0.26.x は torch 2.11 train)。"""
    stack = _load_module(TORCH_STACK_SCRIPT, "vllm_base_torch_stack")
    assert stack.TORCH_STACK["torch"].startswith("2.12.1")
    assert stack.TORCH_STACK["torchvision"].startswith("0.27.")
    assert stack.PYTORCH_INDEX == "https://download.pytorch.org/whl/cu130"
