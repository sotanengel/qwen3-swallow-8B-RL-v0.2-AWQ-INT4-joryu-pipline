"""MCP 実行時状態とヘルスチェック。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("joryu_status")


@dataclass
class McpRuntimeState:
    enabled: bool
    state: str  # up | down | degraded


def probe_mcp_health(*, url: str, enabled: bool, timeout: float = 3.0) -> McpRuntimeState:
    """起動時に MCP /health を確認し、到達不能なら enabled を降格する。"""
    if not enabled or not url.strip():
        return McpRuntimeState(enabled=False, state="down")
    health_url = url.rstrip("/") + "/health"
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            resp = client.get(health_url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "MCP health check failed; falling back to local tools",
            extra={"mcp.state": "down", "mcp.url": url, "error": str(exc)},
        )
        return McpRuntimeState(enabled=False, state="down")
    logger.info("MCP health check passed", extra={"mcp.state": "up", "mcp.url": url})
    return McpRuntimeState(enabled=True, state="up")


def log_mcp_fallback(*, url: str, reason: str) -> None:
    logger.warning(
        "MCP remote call failed; using local executor",
        extra={"mcp.state": "degraded", "mcp.url": url, "reason": reason},
    )
