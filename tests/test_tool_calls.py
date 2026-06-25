"""tool_calls.py: `<tool_call>` および ```json``` フェンスのパース。"""

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


# ---- #92 ```json``` fence detection ----


def test_extract_json_fence_tool_call() -> None:
    """```json {"name":..., "arguments":...} ``` フェンス内の JSON を抽出。"""
    text = '```json\n{"name": "search", "arguments": {"query": "foo"}}\n```'
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {"query": "foo"}
    assert cleaned == ""


def test_extract_json_fence_with_leading_planning_text() -> None:
    """dialog × tools 漏れの実例: planning 文 + ```json``` フェンス。"""
    text = (
        "以下のように、まず再犯率に関する最新の統計情報を検索し、"
        "その結果を踏まえて議論します。\n\n"
        "```json\n"
        '{"name": "search", "arguments": {"query": "日本の再犯率 刑事司法 罰則", "top_k": 3}}\n'
        "```"
    )
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {
        "query": "日本の再犯率 刑事司法 罰則",
        "top_k": 3,
    }
    # 抽出後の cleaned text は planning 文だけになる
    assert cleaned == (
        "以下のように、まず再犯率に関する最新の統計情報を検索し、その結果を踏まえて議論します。"
    )


def test_mixed_tool_call_tag_and_json_fence() -> None:
    """`<tool_call>` タグと ```json``` フェンスが混在 → 両方抽出。"""
    text = (
        '<tool_call>{"name":"search","arguments":{"query":"a"}}</tool_call>\n'
        "次に計算します。\n\n"
        '```json\n{"name": "calc", "arguments": {"expression": "1+1"}}\n```'
    )
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 2
    names = {c.name for c in calls}
    assert names == {"search", "calc"}
    assert "次に計算します。" in cleaned
    assert "tool_call" not in cleaned
    assert "```json" not in cleaned


def test_json_fence_without_name_arguments_treated_as_code_block() -> None:
    """```json``` 内に `"name"` `"arguments"` が無い → コード例として残す。"""
    text = 'JSON スキーマの例:\n\n```json\n{"type": "object", "properties": {"id": "string"}}\n```'
    calls, cleaned = extract_tool_calls(text)
    assert calls == []
    # コード例として丸ごと残る
    assert "```json" in cleaned
    assert "type" in cleaned
