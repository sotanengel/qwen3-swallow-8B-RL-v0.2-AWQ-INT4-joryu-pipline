"""dashboard 起動後にブラウザを開くヘルパー。"""

from __future__ import annotations

import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Protocol

DASHBOARD_URL = "http://localhost:3000"
DEFAULT_READY_TIMEOUT_S = 120.0
DEFAULT_POLL_INTERVAL_S = 0.5


class _WebBrowser(Protocol):
    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool: ...


def wait_for_dashboard(
    url: str = DASHBOARD_URL,
    *,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
) -> bool:
    """HTTP 200 が返るまでポーリング。タイムアウト時は False。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(poll_interval_s)
    return False


def open_dashboard(
    url: str = DASHBOARD_URL,
    *,
    browser: _WebBrowser | None = None,
) -> None:
    """既定ブラウザで dashboard URL を開く。"""
    opener = browser or webbrowser
    print(f"[joryu-up] opening {url}", file=sys.stderr)
    opener.open(url)


def schedule_open_dashboard(
    url: str = DASHBOARD_URL,
    *,
    wait_fn=wait_for_dashboard,
    open_fn=open_dashboard,
) -> None:
    """バックグラウンドで ready 待ち → ブラウザ起動 (foreground compose 用)。"""

    def _worker() -> None:
        if wait_fn(url):
            open_fn(url)
        else:
            print(
                f"[joryu-up] dashboard not ready at {url}; skipped opening browser",
                file=sys.stderr,
            )

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def open_dashboard_when_ready(
    url: str = DASHBOARD_URL,
    *,
    wait_fn=wait_for_dashboard,
    open_fn=open_dashboard,
) -> None:
    """ready 待ち → ブラウザ起動 (detach 後の同期版)。"""
    if wait_fn(url):
        open_fn(url)
    else:
        print(
            f"[joryu-up] dashboard not ready at {url}; skipped opening browser",
            file=sys.stderr,
        )
