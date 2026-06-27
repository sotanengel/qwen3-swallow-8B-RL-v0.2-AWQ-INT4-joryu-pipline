"""docker compose up 後のサービス ready 待ち。"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

API_HEALTH_URL = "http://localhost:8000/api/health"
VLLM_HEALTH_URL = "http://localhost:8100/health"
MCP_HEALTH_URL = "http://localhost:8200/health"
DASHBOARD_URL = "http://localhost:3000"

DEFAULT_READY_TIMEOUT_S = 120.0
VLLM_READY_TIMEOUT_S = 600.0
DEFAULT_POLL_INTERVAL_S = 0.5


class _UrlOpen(Protocol):
    def __call__(self, url: str, timeout: int = ...) -> Any: ...


def wait_for_http_ok(
    url: str,
    *,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    urlopen_fn: _UrlOpen | None = None,
) -> bool:
    """HTTP 200 が返るまでポーリング。タイムアウト時は False。"""
    opener = urlopen_fn or urllib.request.urlopen
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            pass
        time.sleep(poll_interval_s)
    return False


def wait_for_http_json(
    url: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    urlopen_fn: _UrlOpen | None = None,
) -> bool:
    """JSON レスポンスが predicate を満たすまでポーリング。"""
    opener = urlopen_fn or urllib.request.urlopen
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status != 200:
                    time.sleep(poll_interval_s)
                    continue
                body = resp.read()
                data = json.loads(body.decode("utf-8"))
                if predicate(data):
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(poll_interval_s)
    return False


def wait_for_api(**kwargs: Any) -> bool:
    return wait_for_http_ok(API_HEALTH_URL, **kwargs)


def vllm_health_body_ready(body: bytes) -> bool:
    """``/health`` レスポンスが ready か判定。

    - vllm serve: HTTP 200 + 空ボディ
    - joryu-llm-serve: ``{"status": "ok", ...}``
    """
    text = body.decode("utf-8").strip()
    if not text:
        return True
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def wait_for_vllm_health(
    url: str,
    *,
    timeout_s: float = VLLM_READY_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    urlopen_fn: _UrlOpen | None = None,
) -> bool:
    """vLLM デーモン ``/health`` が ready になるまでポーリング。"""
    opener = urlopen_fn or urllib.request.urlopen
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status == 200 and vllm_health_body_ready(resp.read()):
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            pass
        time.sleep(poll_interval_s)
    return False


def wait_for_vllm_daemon(**kwargs: Any) -> bool:
    kwargs.setdefault("timeout_s", VLLM_READY_TIMEOUT_S)
    return wait_for_vllm_health(VLLM_HEALTH_URL, **kwargs)


def wait_for_dashboard(
    url: str = DASHBOARD_URL,
    **kwargs: Any,
) -> bool:
    return wait_for_http_ok(url, **kwargs)


def wait_for_mcp(**kwargs: Any) -> bool:
    return wait_for_http_ok(MCP_HEALTH_URL, **kwargs)


def resolve_vllm_health_url() -> str:
    """常駐 LLM デーモンの health URL (api コンテナ内は JORYU_VLLM_URL 優先)。"""
    import os

    base = os.environ.get("JORYU_VLLM_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/health"
    return VLLM_HEALTH_URL


def is_vllm_daemon_ready(**kwargs: Any) -> bool:
    """vLLM デーモンが ready か (1 回 GET)。vllm serve / joryu-llm-serve 両対応。"""
    url = kwargs.pop("url", None) or resolve_vllm_health_url()
    urlopen_fn = kwargs.pop("urlopen_fn", None)

    try:
        opener = urlopen_fn or urllib.request.urlopen
        with opener(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            return vllm_health_body_ready(resp.read())
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def wait_for_up_services(
    up_services: list[str],
    *,
    log: Callable[[str], None] | None = None,
) -> bool:
    """up 対象サービスが ready になるまで待つ。失敗時 False。"""
    emit = log or (lambda msg: print(msg, file=sys.stderr))

    if "api" in up_services:
        emit(f"[joryu-up] waiting for API at {API_HEALTH_URL}")
        if not wait_for_api():
            emit(f"[joryu-up] API not ready at {API_HEALTH_URL}")
            return False
        emit("[joryu-up] API ready")

    if "mcp" in up_services:
        emit(f"[joryu-up] waiting for MCP at {MCP_HEALTH_URL}")
        if not wait_for_mcp():
            emit(f"[joryu-up] MCP not ready at {MCP_HEALTH_URL}")
            return False
        emit("[joryu-up] MCP ready")

    if "joryu" in up_services:
        emit(f"[joryu-up] waiting for vLLM daemon at {VLLM_HEALTH_URL}")
        if not wait_for_vllm_daemon():
            emit(f"[joryu-up] vLLM daemon not ready at {VLLM_HEALTH_URL}")
            return False
        emit("[joryu-up] vLLM daemon ready")

    if "dashboard" in up_services:
        emit(f"[joryu-up] waiting for dashboard at {DASHBOARD_URL}")
        if not wait_for_dashboard():
            emit(f"[joryu-up] dashboard not ready at {DASHBOARD_URL}")
            return False
        emit("[joryu-up] dashboard ready")

    return True
