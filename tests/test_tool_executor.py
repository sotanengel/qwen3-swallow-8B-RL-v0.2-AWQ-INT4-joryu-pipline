"""tool_executor.py: スタブと calc レジストリ。"""

import pytest

from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import RegistryToolExecutor, StubToolExecutor, build_default_executor


def test_stub_executor_returns_fixed() -> None:
    ex = StubToolExecutor({"search": "mock results"})
    assert ex.run(ParsedToolCall(name="search", arguments={"q": "x"}, raw="")) == "mock results"


def test_stub_executor_default_message() -> None:
    ex = StubToolExecutor()
    out = ex.run(ParsedToolCall(name="calc", arguments={"expression": "1+1"}, raw=""))
    assert "stub:calc" in out


def test_registry_calc_evaluates() -> None:
    ex = build_default_executor()
    out = ex.run(ParsedToolCall(name="calc", arguments={"expression": "2+3"}, raw=""))
    assert out == "5"


def test_registry_unknown_tool_raises() -> None:
    ex = RegistryToolExecutor()
    with pytest.raises(KeyError):
        ex.run(ParsedToolCall(name="missing", arguments={}, raw=""))


def test_default_executor_search_returns_query_specific_stub() -> None:
    ex = build_default_executor()
    out = ex.run(
        ParsedToolCall(name="search", arguments={"query": "日本の再犯率", "top_k": 3}, raw="")
    )
    assert "日本の再犯率" in out
    assert "snippet" in out.lower() or "スニペット" in out or "result" in out.lower()


def test_default_executor_fetch_url_returns_url_specific_stub() -> None:
    ex = build_default_executor()
    url = "https://example.com/stats"
    out = ex.run(ParsedToolCall(name="fetch_url", arguments={"url": url}, raw=""))
    assert url in out
