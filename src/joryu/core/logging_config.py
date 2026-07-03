"""集中ロギング設定。"""

from __future__ import annotations

import logging
import sys


def setup_logging(*, level: int = logging.INFO) -> None:
    """stderr へ basicConfig を適用する (既存 handler があれば上書きしない)。"""
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
