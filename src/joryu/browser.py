"""dashboard 起動後にブラウザを開くヘルパー。"""

from __future__ import annotations

import sys
import threading
import webbrowser
from collections.abc import Callable
from typing import Protocol

from joryu.readiness import DASHBOARD_URL, wait_for_dashboard

DEFAULT_READY_TIMEOUT_S = 120.0


class _WebBrowser(Protocol):
    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool: ...


def open_dashboard(
    url: str = DASHBOARD_URL,
    *,
    browser: _WebBrowser | None = None,
) -> None:
    """既定ブラウザで dashboard URL を開く。"""
    print(f"[joryu-up] opening {url}", file=sys.stderr)
    if browser is not None:
        browser.open(url)
        return
    if sys.platform == "win32":
        import os

        os.startfile(url)  # type: ignore[attr-defined,no-untyped-call]
        return
    webbrowser.open(url)


def schedule_open_dashboard(
    url: str = DASHBOARD_URL,
    *,
    wait_fn=wait_for_dashboard,
    open_fn=open_dashboard,
    pre_open_fn: Callable[[], None] | None = None,
) -> None:
    """バックグラウンドで ready 待ち → ブラウザ起動 (foreground compose 用)。"""

    def _worker() -> None:
        if wait_fn(url):
            if pre_open_fn is not None:
                pre_open_fn()
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
    pre_open_fn: Callable[[], None] | None = None,
) -> None:
    """ready 待ち → ブラウザ起動 (detach 後の同期版)。"""
    if wait_fn(url):
        if pre_open_fn is not None:
            pre_open_fn()
        open_fn(url)
    else:
        print(
            f"[joryu-up] dashboard not ready at {url}; skipped opening browser",
            file=sys.stderr,
        )
