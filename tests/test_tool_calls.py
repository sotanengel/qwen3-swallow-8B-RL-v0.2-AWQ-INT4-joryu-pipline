"""tool_calls.py: `<tool_call>` パース。"""

from joryu.tool_calls import ParsedToolCall, extract_tool_calls


def test_extract_single_tool_call() -> None:
    text = '<tool_call>{"name":"search","arguments":{"query":"foo"}}</tool_call>'
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {"query": "foo"}
    assert cleaned == ""


def test_extract_two_tool_calls() -> None:
    text = (
        '<tool_call>{"name":"search","arguments":{"query":"a"}}</tool_call>'
        '<tool_call>{"name":"calc","arguments":{"expression":"1+1"}}</tool_call>'
    )
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 2
    assert calls[0].name == "search"
    assert calls[1].name == "calc"
    assert cleaned == ""


def test_malformed_json_preserved() -> None:
    text = "<tool_call>{not json}</tool_call>"
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "<malformed>"
    assert calls[0].arguments == {}
    assert calls[0].raw == "{not json}"


def test_text_after_tool_call_remains() -> None:
    text = '<tool_call>{"name":"search","arguments":{"query":"foo"}}</tool_call>\n最終回答です。'
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert isinstance(calls[0], ParsedToolCall)
    assert cleaned == "最終回答です。"
