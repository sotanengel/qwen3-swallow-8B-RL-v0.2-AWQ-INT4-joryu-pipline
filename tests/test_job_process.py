"""job_process のテスト。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from joryu.job_process import JobProcess, terminate_process_tree


def test_lifecycle_terminate_process_tree_waits_for_graceful_exit(tmp_path: Path) -> None:
    if sys.platform == "win32":
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    else:
        cmd = ["sleep", "30"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def _stop_later() -> None:
        time.sleep(0.2)
        terminate_process_tree(proc, wait_timeout_s=1.0)

    threading.Thread(target=_stop_later, daemon=True).start()
    rc = terminate_process_tree(proc, wait_timeout_s=5.0)
    assert proc.poll() is not None
    assert rc is not None


def test_lifecycle_job_process_context_manager_terminates_on_exit(tmp_path: Path) -> None:
    log_path = tmp_path / "job.log"
    terminated: list[str] = []

    class _RunningProc:
        stdout = iter([])

        def poll(self) -> int | None:
            return None

        def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
            return 0

        def terminate(self) -> None:
            terminated.append("terminate")

        def kill(self) -> None:
            terminated.append("kill")

    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _RunningProc()

    with JobProcess(["sleep", "999"], cwd=tmp_path, log_path=log_path, popen=fake_popen):
        pass

    assert terminated


def test_job_process_writes_command_to_log(tmp_path: Path) -> None:
    log_path = tmp_path / "job.log"

    class _DummyProc:
        def __init__(self) -> None:
            self.stdout = iter(["ok\n"])
            self.pid = 12345

        def poll(self) -> int | None:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _DummyProc()

    with JobProcess(["echo", "hello"], cwd=tmp_path, log_path=log_path, popen=fake_popen) as job:
        rc = job.stream_to_log()

    assert rc == 0
    text = log_path.read_text(encoding="utf-8")
    assert "echo hello" in text
    assert "ok" in text
