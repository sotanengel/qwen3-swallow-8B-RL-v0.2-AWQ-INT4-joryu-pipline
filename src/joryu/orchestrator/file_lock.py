"""active_profile.json のファイルロック。"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def file_lock(path: Path, *, timeout_s: float = 30.0) -> Iterator[None]:
    """排他ロック。Linux は fcntl、Windows は msvcrt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.touch(exist_ok=True)
    with lock_path.open("a+b") as fh:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            deadline = os.times()[4] + timeout_s
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if os.times()[4] >= deadline:
                        raise TimeoutError(f"file lock timeout: {lock_path}") from None
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
