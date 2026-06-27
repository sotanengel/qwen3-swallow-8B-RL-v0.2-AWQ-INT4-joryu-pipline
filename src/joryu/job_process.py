"""subprocess ライフサイクル管理。"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)

TerminateFn = Callable[[subprocess.Popen[str]], None]


def _default_terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        send_signal = getattr(proc, "send_signal", None)
        if callable(send_signal):
            try:
                send_signal(subprocess.signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                return
            except (OSError, AttributeError, ValueError):
                pass
        pid = getattr(proc, "pid", None)
        if isinstance(pid, int):
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                check=False,
                capture_output=True,
                text=True,
            )
            return
    proc.terminate()


def terminate_process_tree(
    proc: subprocess.Popen[str],
    *,
    wait_timeout_s: float = 5.0,
    terminate_fn: TerminateFn | None = None,
    kill_fn: Callable[[subprocess.Popen[str]], None] | None = None,
) -> int | None:
    """terminate → wait → kill の順で子プロセスを停止する。"""
    if proc.poll() is not None:
        return proc.returncode

    stop = terminate_fn or _default_terminate
    stop(proc)
    try:
        return proc.wait(timeout=wait_timeout_s)
    except subprocess.TimeoutExpired:
        logger.warning(
            "[job_process] process did not exit in %ss; killing pid=%s",
            wait_timeout_s,
            getattr(proc, "pid", "?"),
        )
        if kill_fn is not None:
            kill_fn(proc)
        else:
            proc.kill()
        return proc.wait(timeout=wait_timeout_s)


class JobProcess:
    """Popen を context manager で包み、終了時に確実に teardown する。"""

    def __init__(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        log_path: Path,
        popen: Callable[..., subprocess.Popen[str]] | None = None,
    ) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.log_path = log_path
        self._popen = popen or subprocess.Popen
        self.proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> JobProcess:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_fh:
            log_fh.write(f"[joryu-runner] {' '.join(self.cmd)}\n")
            log_fh.flush()
        self.proc = self._popen(
            self.cmd,
            cwd=str(self.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
            ),
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        if self.proc is None:
            return
        if self.proc.poll() is None:
            terminate_process_tree(self.proc)
        self.proc = None

    def stream_to_log(self) -> int:
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("JobProcess is not started")
        with self.log_path.open("a", encoding="utf-8") as log_fh:
            for line in self.proc.stdout:
                log_fh.write(line)
                log_fh.flush()
        return self.proc.wait()
