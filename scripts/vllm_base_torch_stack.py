"""joryu-vllm-base の torch/torchvision/torchaudio pin SSOT。

Dockerfile.vllm-base と pytest 契約テストは本モジュールを参照すること。
"""

from __future__ import annotations

TORCH_STACK: dict[str, str] = {
    "torch": "2.12.1+cu130",
    "torchvision": "0.27.1+cu130",
    "torchaudio": "2.11.0+cu130",
}

PYTORCH_INDEX = "https://download.pytorch.org/whl/cu130"
