"""CLI / ジョブ向け hard deadline (POSIX alarm / Windows timer)。"""

from __future__ import annotations

import signal
import sys
import threading


def install_hard_deadline(seconds: int) -> None:
    """指定秒後にプロセスを終了する hard deadline を設定する。"""
    if seconds <= 0:
        return

    def _exit_deadline() -> None:
        sys.exit(143)

    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, lambda _signum, _frame: _exit_deadline())
        signal.alarm(seconds)
        return

    timer = threading.Timer(seconds, _exit_deadline)
    timer.daemon = True
    timer.start()
