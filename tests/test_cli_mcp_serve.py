"""joryu-mcp CLI smoke。"""

from __future__ import annotations

import subprocess
import sys


def test_joryu_mcp_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "joryu.cli.mcp_serve", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--stdio" in proc.stdout
