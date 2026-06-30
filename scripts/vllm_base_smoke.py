"""joryu-vllm-base ビルド時 smoke: vllm serve と同じ import 経路を検証する。"""

from __future__ import annotations

import sys


def main() -> None:
    import torch
    import torchvision
    import vllm._C  # noqa: F401
    import vllm.entrypoints.cli.main  # noqa: F401
    from transformers.image_utils import load_image  # noqa: F401

    if not torch.__version__.startswith("2.12.1"):
        msg = f"unexpected torch version: {torch.__version__}"
        raise AssertionError(msg)
    if not torchvision.__version__.startswith("0.27."):
        msg = f"unexpected torchvision version: {torchvision.__version__}"
        raise AssertionError(msg)

    print(
        "vllm-base smoke OK",
        torch.__version__,
        torchvision.__version__,
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
