"""logging_config のテスト。"""

from __future__ import annotations

import logging
import sys

from joryu.logging_config import setup_logging


def test_setup_logging_uses_stderr(capsys) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)

    setup_logging(level=logging.INFO)

    logger = logging.getLogger("joryu.test.logging")
    logger.info("logging-config-marker")

    captured = capsys.readouterr()
    assert "logging-config-marker" in captured.err
    assert captured.out == ""
    assert root.handlers
    assert any(getattr(h, "stream", None) is sys.stderr for h in root.handlers)
