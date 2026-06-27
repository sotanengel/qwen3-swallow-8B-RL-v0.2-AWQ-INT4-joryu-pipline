"""tools_impl.search のテスト。"""

from __future__ import annotations

import httpx
import respx

from joryu.tools_impl.search import TavilyProvider, web_search


@respx.mock
def test_tavily_provider_parses_response() -> None:
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "東京の天気",
                        "url": "https://tenki.jp/",
                        "content": "今日は晴れ",
                    }
                ]
            },
        )
    )
    provider = TavilyProvider("test-key")
    results = provider.search("今日の東京の天気 2026", 3)
    assert results[0].title == "東京の天気"
    assert "tenki.jp" in results[0].url


@respx.mock
def test_tavily_provider_builds_request() -> None:
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    TavilyProvider("secret-key").search("query", 2)
    body = route.calls.last.request.content.decode()
    assert "secret-key" in body
    assert "query" in body


def test_search_fn_falls_back_to_stub_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("JORYU_SEARCH_PROVIDER", "tavily")
    out = web_search("今日の東京の天気", top_k=2)
    assert "今日の東京の天気" in out
    assert "stub" in out.lower()


def test_search_fn_truncates_query() -> None:
    long_q = "x" * 300
    from joryu.tools_impl.search import _truncate_query

    assert len(_truncate_query(long_q)) == 256
