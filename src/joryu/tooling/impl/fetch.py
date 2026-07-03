"""URL 本文取得 (SSRF 対策付き)。"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "joryu-bot/0.1 (+https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline)"
)
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_BYTES = 512_000
TEXT_TRUNCATE = 8000


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast:
        return True
    if str(ip) == "169.254.169.254":
        return True
    return False


def _validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("fetch_url supports http/https only")
    host = parsed.hostname
    if not host:
        raise ValueError("fetch_url requires a valid host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve host: {host!r}") from exc
    for info in infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        if _is_blocked_ip(ip):
            raise ValueError(f"blocked URL (private/reserved IP): {url!r}")
    return url.strip()


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    body = soup.get_text(separator="\n", strip=True)
    if title:
        return f"Title: {title}\nBody: {body}"
    return body


def fetch_url(url: str, *, max_bytes: int | None = None, timeout: float | None = None) -> str:
    validated = _validate_url(url)
    limit = (
        max_bytes if max_bytes is not None else _env_int("JORYU_FETCH_MAX_BYTES", DEFAULT_MAX_BYTES)
    )
    to = timeout if timeout is not None else _env_float("JORYU_FETCH_TIMEOUT", DEFAULT_TIMEOUT)
    headers = {"User-Agent": USER_AGENT}
    httpx_timeout = httpx.Timeout(connect=5.0, read=to, write=5.0, pool=5.0)
    with httpx.Client(timeout=httpx_timeout, follow_redirects=True) as client:
        resp = client.get(validated, headers=headers)
        resp.raise_for_status()
        raw = resp.content[:limit]
        content_type = resp.headers.get("content-type", "")

    if "text/html" in content_type.lower():
        text = _extract_text(raw.decode(resp.encoding or "utf-8", errors="replace"))
    else:
        text = raw.decode(resp.encoding or "utf-8", errors="replace")

    if len(text) > TEXT_TRUNCATE:
        return text[:TEXT_TRUNCATE] + "\n[truncated]"
    return text
