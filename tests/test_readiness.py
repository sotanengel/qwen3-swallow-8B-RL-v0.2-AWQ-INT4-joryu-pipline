"""readiness.py: サービス ready 待ちのユニットテスト。"""

from __future__ import annotations

import json
import urllib.error

import pytest

from joryu.readiness import (
    API_HEALTH_URL,
    VLLM_HEALTH_URL,
    wait_for_api,
    wait_for_http_ok,
    wait_for_vllm_daemon,
)


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_wait_for_http_ok_returns_true_on_200() -> None:
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("refused")
        return _FakeResponse(200)

    assert wait_for_http_ok("http://example/", urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=1)


def test_wait_for_http_ok_returns_false_on_timeout() -> None:
    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        raise urllib.error.URLError("down")

    assert (
        wait_for_http_ok(
            "http://example/",
            urlopen_fn=_urlopen,
            poll_interval_s=0,
            timeout_s=0.01,
        )
        is False
    )


def test_wait_for_vllm_daemon_accepts_status_ok_without_model_loaded() -> None:
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(503, json.dumps({"status": "loading"}).encode())
        return _FakeResponse(200, json.dumps({"status": "ok"}).encode())

    assert wait_for_vllm_daemon(urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=1)


def test_wait_for_vllm_daemon_accepts_joryu_model_loaded_response() -> None:
    body = json.dumps({"status": "ok", "model_loaded": True}).encode()

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        return _FakeResponse(200, body)

    assert wait_for_vllm_daemon(urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=1)


def test_wait_for_api_uses_health_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _wait(url: str, **kwargs: object) -> bool:
        seen.append(url)
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_http_ok", _wait)
    assert wait_for_api()
    assert seen == [API_HEALTH_URL]


def test_wait_for_dashboard_accepts_custom_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _wait(url: str, **kwargs: object) -> bool:
        del kwargs
        seen.append(url)
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_http_ok", _wait)
    from joryu.readiness import wait_for_dashboard

    assert wait_for_dashboard("http://custom:3000")
    assert seen == ["http://custom:3000"]


def test_wait_for_vllm_daemon_uses_default_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _wait(url: str, _predicate: object, **kwargs: object) -> bool:
        del _predicate, kwargs
        seen.append(url)
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_http_json", _wait)
    wait_for_vllm_daemon()
    assert seen == [VLLM_HEALTH_URL]
