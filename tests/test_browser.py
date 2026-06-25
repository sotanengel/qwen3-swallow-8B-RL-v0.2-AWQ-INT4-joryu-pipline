"""browser.py: dashboard 起動待ちとブラウザ起動のユニットテスト。"""

from __future__ import annotations

import urllib.error

import pytest

from joryu.browser import (
    DASHBOARD_URL,
    open_dashboard,
    open_dashboard_when_ready,
    schedule_open_dashboard,
)
from joryu.readiness import wait_for_dashboard


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeBrowser:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        self.urls.append(url)
        return True


def test_wait_for_dashboard_returns_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse(200)

    monkeypatch.setattr("joryu.readiness.urllib.request.urlopen", _urlopen)
    assert wait_for_dashboard(poll_interval_s=0, timeout_s=1)


def test_wait_for_dashboard_returns_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        raise urllib.error.URLError("down")

    monkeypatch.setattr("joryu.readiness.urllib.request.urlopen", _urlopen)
    assert wait_for_dashboard(poll_interval_s=0, timeout_s=0.01) is False


def test_open_dashboard_uses_browser(capsys: pytest.CaptureFixture[str]) -> None:
    browser = _FakeBrowser()
    open_dashboard(DASHBOARD_URL, browser=browser)
    assert browser.urls == [DASHBOARD_URL]
    assert "opening" in capsys.readouterr().err


def test_open_dashboard_uses_startfile_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("joryu.browser.sys.platform", "win32")

    def _startfile(url: str) -> None:
        opened.append(url)

    monkeypatch.setattr("os.startfile", _startfile, raising=False)
    open_dashboard(DASHBOARD_URL)
    assert opened == [DASHBOARD_URL]
    assert "opening" in capsys.readouterr().err


def test_open_dashboard_when_ready_skips_if_not_ready(capsys: pytest.CaptureFixture[str]) -> None:
    open_dashboard_when_ready(wait_fn=lambda _url: False, open_fn=lambda **_kw: None)
    err = capsys.readouterr().err
    assert "skipped opening browser" in err


def test_open_dashboard_when_ready_runs_pre_open_fn_before_open() -> None:
    order: list[str] = []

    open_dashboard_when_ready(
        wait_fn=lambda _url: True,
        pre_open_fn=lambda: order.append("cleanup"),
        open_fn=lambda _url, **_kw: order.append("open"),
    )
    assert order == ["cleanup", "open"]


def test_schedule_open_dashboard_runs_pre_open_fn_before_open() -> None:
    order: list[str] = []

    schedule_open_dashboard(
        wait_fn=lambda _url: True,
        pre_open_fn=lambda: order.append("cleanup"),
        open_fn=lambda _url, **_kw: order.append("open"),
    )
    import time

    deadline = time.monotonic() + 2
    while len(order) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert order == ["cleanup", "open"]


def test_schedule_open_dashboard_starts_thread() -> None:
    opened: list[str] = []

    def _open(url: str = DASHBOARD_URL, **kwargs: object) -> None:
        opened.append(url)

    schedule_open_dashboard(wait_fn=lambda _url: True, open_fn=_open)
    import time

    deadline = time.monotonic() + 2
    while not opened and time.monotonic() < deadline:
        time.sleep(0.01)
    assert opened == [DASHBOARD_URL]
