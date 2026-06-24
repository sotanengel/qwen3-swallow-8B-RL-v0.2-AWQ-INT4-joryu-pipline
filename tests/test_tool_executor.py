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
