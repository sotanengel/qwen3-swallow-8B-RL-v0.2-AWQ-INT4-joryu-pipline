"""readiness.py: サービス ready 待ちのユニットテスト。"""

from __future__ import annotations

import json
import urllib.error

import pytest

from joryu.readiness import (
    API_HEALTH_URL,
    MCP_HEALTH_URL,
    VLLM_HEALTH_URL,
    vllm_health_body_ready,
    wait_for_api,
    wait_for_http_ok,
    wait_for_mcp,
    wait_for_up_services,
    wait_for_vllm_daemon,
    wait_for_vllm_health,
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


def test_vllm_health_body_ready_accepts_empty_body() -> None:
    assert vllm_health_body_ready(b"") is True
    assert vllm_health_body_ready(b"  \n") is True


def test_vllm_health_body_ready_rejects_json_body() -> None:
    body = json.dumps({"status": "ok", "model_loaded": True}).encode()
    assert vllm_health_body_ready(body) is False


def test_llama_server_health_ready() -> None:
    from joryu.orchestrator.profile import ProfileSpec
    from joryu.readiness import is_profile_healthy, llama_server_health_ready

    assert llama_server_health_ready(json.dumps({"status": "ok"}).encode()) is True
    assert llama_server_health_ready(b"{}") is False

    spec = ProfileSpec(
        name="screening",
        service="joryu-judge",
        port=8080,
        kind="llama_server",
    )

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        return _FakeResponse(200, json.dumps({"status": "ok"}).encode())

    assert is_profile_healthy(spec, urlopen_fn=_urlopen) is True


def test_wait_for_profile_daemon_success() -> None:
    from joryu.orchestrator.profile import ProfileSpec
    from joryu.readiness import wait_for_profile_daemon

    spec = ProfileSpec(name="distill", service="joryu", port=8100)
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("down")
        return _FakeResponse(200, b"")

    assert wait_for_profile_daemon(spec, urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=1)


def test_wait_for_vllm_health_accepts_empty_200_body() -> None:
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("refused")
        return _FakeResponse(200, b"")

    assert wait_for_vllm_health(
        "http://example/health",
        urlopen_fn=_urlopen,
        poll_interval_s=0,
        timeout_s=1,
    )


def test_wait_for_vllm_daemon_retries_until_empty_200_body() -> None:
    calls = {"n": 0}

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(503, b"")
        return _FakeResponse(200, b"")

    assert wait_for_vllm_daemon(urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=1)


def test_wait_for_vllm_daemon_rejects_json_body() -> None:
    body = json.dumps({"status": "ok", "model_loaded": True}).encode()

    def _urlopen(url: str, timeout: int = 0) -> _FakeResponse:
        return _FakeResponse(200, body)

    assert wait_for_vllm_daemon(urlopen_fn=_urlopen, poll_interval_s=0, timeout_s=0.01) is False


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

    def _wait(url: str, **kwargs: object) -> bool:
        del kwargs
        seen.append(url)
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_vllm_health", _wait)
    wait_for_vllm_daemon()
    assert seen == [VLLM_HEALTH_URL]


def test_wait_for_mcp_uses_health_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _wait(url: str, **kwargs: object) -> bool:
        seen.append(url)
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_http_ok", _wait)
    assert wait_for_mcp()
    assert seen == [MCP_HEALTH_URL]


def test_wait_for_up_services_waits_for_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    def _api(**kwargs: object) -> bool:
        del kwargs
        order.append("api")
        return True

    def _mcp(**kwargs: object) -> bool:
        del kwargs
        order.append("mcp")
        return True

    def _vllm(**kwargs: object) -> bool:
        del kwargs
        order.append("vllm")
        return True

    def _dash(**kwargs: object) -> bool:
        del kwargs
        order.append("dashboard")
        return True

    monkeypatch.setattr("joryu.readiness.wait_for_api", _api)
    monkeypatch.setattr("joryu.readiness.wait_for_mcp", _mcp)
    monkeypatch.setattr("joryu.readiness.wait_for_vllm_daemon", _vllm)
    monkeypatch.setattr("joryu.readiness.wait_for_dashboard", _dash)
    assert wait_for_up_services(["dashboard", "mcp", "api", "joryu"]) is True
    assert order == ["api", "mcp", "vllm", "dashboard"]
