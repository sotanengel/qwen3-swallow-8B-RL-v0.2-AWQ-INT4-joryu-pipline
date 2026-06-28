"""docker compose up 後のサービス ready 待ち。"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from joryu.utils.retry import ExponentialBackoff

API_HEALTH_URL = "http://localhost:8000/api/health"
VLLM_HEALTH_URL = "http://localhost:8100/health"
MCP_HEALTH_URL = "http://localhost:8200/health"
DASHBOARD_URL = "http://localhost:3000"

DEFAULT_READY_TIMEOUT_S = 120.0
VLLM_READY_TIMEOUT_S = 600.0
DEFAULT_POLL_INTERVAL_S = 0.5

logger = logging.getLogger(__name__)


class _UrlOpen(Protocol):
    def __call__(self, url: str, timeout: int = ...) -> Any: ...


def _poll_backoff_delay(attempt: int, *, poll_interval_s: float) -> float:
    if poll_interval_s <= 0:
        return 0.0
    policy = ExponentialBackoff(
        base=max(poll_interval_s * 0.25, 0.05),
        max_delay=poll_interval_s,
        jitter=0.1,
    )
    return policy.delay_for_attempt(attempt)


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
    attempt = 0
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            pass
        time.sleep(_poll_backoff_delay(attempt, poll_interval_s=poll_interval_s))
        attempt += 1
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
    attempt = 0
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status != 200:
                    time.sleep(_poll_backoff_delay(attempt, poll_interval_s=poll_interval_s))
                    attempt += 1
                    continue
                body = resp.read()
                data = json.loads(body.decode("utf-8"))
                if predicate(data):
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(_poll_backoff_delay(attempt, poll_interval_s=poll_interval_s))
        attempt += 1
    return False


def wait_for_api(**kwargs: Any) -> bool:
    return wait_for_http_ok(API_HEALTH_URL, **kwargs)


def vllm_health_body_ready(body: bytes) -> bool:
    """``/health`` レスポンスが ready か判定 (vllm serve: HTTP 200 + 空ボディ)。"""
    return not body.decode("utf-8").strip()


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
    attempt = 0
    while time.monotonic() < deadline:
        try:
            with opener(url, timeout=2) as resp:
                if resp.status == 200 and vllm_health_body_ready(resp.read()):
                    return True
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            pass
        time.sleep(_poll_backoff_delay(attempt, poll_interval_s=poll_interval_s))
        attempt += 1
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
    """vLLM デーモンが ready か (1 回 GET)。vllm serve の空ボディ /health を想定。"""
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


def llama_server_health_ready(body: bytes) -> bool:
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return data.get("status") == "ok"


def is_profile_healthy(spec: Any, *, urlopen_fn: _UrlOpen | None = None) -> bool:
    """ProfileSpec の kind に応じて 1 回 health チェック。"""
    from joryu.orchestrator.profile import ProfileSpec

    if not isinstance(spec, ProfileSpec):
        return False
    url = spec.health_url()
    opener = urlopen_fn or urllib.request.urlopen
    try:
        with opener(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            body = resp.read()
            if spec.kind == "llama_server":
                return llama_server_health_ready(body)
            return vllm_health_body_ready(body)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def is_profile_ready(profile_name: str, profiles: dict[Any, Any], **kwargs: Any) -> bool:
    """名前指定で profile ready を判定。"""
    from joryu.orchestrator.profile import ModelProfile

    try:
        mp = ModelProfile(profile_name)
    except ValueError:
        return False
    spec = profiles.get(mp)
    if spec is None:
        return False
    return is_profile_healthy(spec, urlopen_fn=kwargs.get("urlopen_fn"))


def wait_for_profile_daemon(spec: Any, **kwargs: Any) -> bool:
    """ProfileSpec の health が ready になるまで待つ。"""
    timeout_s = kwargs.pop("timeout_s", DEFAULT_READY_TIMEOUT_S)
    poll_interval_s = kwargs.pop("poll_interval_s", DEFAULT_POLL_INTERVAL_S)
    urlopen_fn = kwargs.get("urlopen_fn")
    deadline = time.monotonic() + timeout_s
    attempt = 0
    while time.monotonic() < deadline:
        if is_profile_healthy(spec, urlopen_fn=urlopen_fn):
            return True
        time.sleep(_poll_backoff_delay(attempt, poll_interval_s=poll_interval_s))
        attempt += 1
    return False


def wait_for_up_services(
    up_services: list[str],
    *,
    log: Callable[[str], None] | None = None,
) -> bool:
    """up 対象サービスが ready になるまで待つ。失敗時 False。"""
    emit = log or (lambda msg: logger.info("%s", msg))

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
