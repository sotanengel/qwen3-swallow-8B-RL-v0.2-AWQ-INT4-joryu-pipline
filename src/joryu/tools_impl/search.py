"""Web 検索 (Tavily / stub)。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
MAX_QUERY_LEN = 256
MAX_TOP_K = 10
DEFAULT_TIMEOUT = 8.0


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    def search(self, query: str, top_k: int) -> list[SearchResult]: ...


def _truncate_query(query: str) -> str:
    q = query.strip()
    if len(q) <= MAX_QUERY_LEN:
        return q
    return q[:MAX_QUERY_LEN]


class StubProvider:
    def search(self, query: str, top_k: int) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"stub result #{i}",
                url=f"https://example.com/{i}",
                snippet=f"「{query}」に関する参考情報 (stub #{i})",
            )
            for i in range(1, min(top_k, 5) + 1)
        ]


class TavilyProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        body = {
            "api_key": self._api_key,
            "query": query,
            "max_results": top_k,
            "search_depth": "basic",
            "include_answer": False,
        }
        with httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT)) as client:
            resp = client.post(TAVILY_URL, json=body)
            resp.raise_for_status()
            payload = resp.json()
        out: list[SearchResult] = []
        for item in payload.get("results") or []:
            out.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("content") or item.get("snippet") or ""),
                )
            )
        return out


def _resolve_provider() -> SearchProvider:
    provider_name = os.environ.get("JORYU_SEARCH_PROVIDER", "tavily").lower()
    if provider_name == "stub":
        return StubProvider()
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.warning("search provider not configured, returning stub")
        return StubProvider()
    return TavilyProvider(api_key)


def format_search_results(query: str, top_k: int, results: list[SearchResult]) -> str:
    lines = [f"[search results for {query!r}, top_k={top_k}]"]
    for i, item in enumerate(results, start=1):
        lines.append(f"{i}. {item.title}")
        if item.url:
            lines.append(f"   url: {item.url}")
        if item.snippet:
            lines.append(f"   snippet: {item.snippet}")
    return "\n".join(lines)


def web_search(query: str, top_k: int = 5) -> str:
    q = _truncate_query(query)
    if not q:
        raise ValueError("search requires string 'query'")
    k = max(1, min(top_k, MAX_TOP_K))
    provider = _resolve_provider()
    results = provider.search(q, k)
    return format_search_results(q, k, results)
