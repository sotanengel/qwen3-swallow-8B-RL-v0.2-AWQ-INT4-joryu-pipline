"""tool_calls.py: `<tool_call>` および ```json``` フェンスのパース。"""

from joryu.tool_calls import (
    ParsedToolCall,
    extract_tool_calls,
    extract_tool_calls_with_diagnostics,
)


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


def test_extract_pretty_printed_multiline_json_fence() -> None:
    """改行・インデント入り整形 JSON をフェンスから抽出。"""
    text = (
        "まず検索します。\n\n"
        "```json\n"
        "{\n"
        '  "name": "search",\n'
        '  "arguments": {\n'
        '    "query": "日本の再犯率",\n'
        '    "top_k": 5\n'
        "  }\n"
        "}\n"
        "```"
    )
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {"query": "日本の再犯率", "top_k": 5}
    assert cleaned == "まず検索します。"


def test_extract_nested_arguments_in_tool_call_tag() -> None:
    """`<tool_call>` 内のネスト JSON arguments を balanced brace で抽出。"""
    text = (
        '<tool_call>{"name":"search","arguments":{"query":"x","filters":{"year":2024}}}</tool_call>'
    )
    calls, cleaned = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].arguments == {"query": "x", "filters": {"year": 2024}}
    assert cleaned == ""


# ---- #103 bare JSON (タグ・フェンス無し) 形式の検出 ----


def test_bare_json_without_known_tool_names_not_extracted() -> None:
    """known_tool_names を指定しない場合、bare JSON は抽出しない (旧互換)。"""
    text = '{"name": "search", "arguments": {"query": "x"}}'
    calls, cleaned = extract_tool_calls(text)
    assert calls == []
    # bare JSON は cleaned に残る
    assert '"name"' in cleaned


def test_bare_json_with_matching_known_tool_extracted() -> None:
    """known_tool_names に一致する bare JSON を抽出。"""
    text = '{"name": "search", "arguments": {"query": "背景音楽 認知"}}'
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search", "calc"})
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {"query": "背景音楽 認知"}
    assert cleaned == ""


def test_bare_json_with_unknown_tool_not_extracted() -> None:
    """known_tool_names に無いツール名の bare JSON は抽出しない (false positive 防止)。"""
    text = '{"name": "rm_rf", "arguments": {"path": "/"}}'
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search"})
    assert calls == []
    assert '"name"' in cleaned


def test_bare_json_with_planning_preamble_extracted() -> None:
    """data/distilled/responses.jsonl idx=5 系実例: planning 文 + bare JSON。"""
    text = (
        "So we should call search with a query about background music.\n\n"
        "We'll call search.\n\n"
        "{\n"
        '  "name": "search",\n'
        '  "arguments": {"query": "背景音楽 思考 生産性", "top_k": 5}\n'
        "}"
    )
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search"})
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments == {
        "query": "背景音楽 思考 生産性",
        "top_k": 5,
    }
    assert "We'll call search." in cleaned
    assert '"name"' not in cleaned


def test_bare_json_multiple_objects_in_text_only_first_tool_payload_extracted() -> None:
    """偶然 JSON が複数ある場合、tool_call 形 (name+arguments+known) のみ拾う。"""
    text = (
        '前段: {"score": 0.7}\n{"name": "search", "arguments": {"query": "x"}}\n後段: {"id": "abc"}'
    )
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search"})
    assert len(calls) == 1
    assert calls[0].name == "search"
    # tool_call 形以外の JSON はそのまま残る
    assert '"score"' in cleaned
    assert '"id"' in cleaned


def test_bare_json_inside_tool_call_tag_not_double_extracted() -> None:
    """既に <tool_call> タグで囲われている場合、bare JSON 検出が二重抽出しない。"""
    text = '<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>'
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search"})
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert cleaned == ""


def test_bare_json_inside_json_fence_not_double_extracted() -> None:
    """既に ```json``` フェンスで囲われている場合、bare JSON 検出が二重抽出しない。"""
    text = '```json\n{"name": "search", "arguments": {"query": "x"}}\n```'
    calls, cleaned = extract_tool_calls(text, known_tool_names={"search"})
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert cleaned == ""


# ---- #103 extract_tool_calls_with_diagnostics ----


def test_diagnostics_returns_no_hints_when_no_residual() -> None:
    """tool_call をきれいに抽出した後、残骸が無ければ hints は空。"""
    text = '<tool_call>{"name":"search","arguments":{"query":"x"}}</tool_call>'
    calls, cleaned, diagnostics = extract_tool_calls_with_diagnostics(text)
    assert len(calls) == 1
    assert cleaned == ""
    assert diagnostics["suspected_unparsed_tool_calls"] == []


def test_diagnostics_detects_bare_json_when_no_known_tool_names() -> None:
    """known_tool_names を指定しない bare JSON は parser を通らないが、診断で検出される。"""
    text = '前置きの文章。\n\n{"name": "search", "arguments": {"query": "x"}}\nあとがき。'
    calls, cleaned, diagnostics = extract_tool_calls_with_diagnostics(text)
    assert calls == []
    hints = diagnostics["suspected_unparsed_tool_calls"]
    assert len(hints) == 1
    assert '"name"' in hints[0]
    assert "search" in hints[0]


def test_diagnostics_detects_orphan_tool_call_open_tag() -> None:
    """`<tool_call>` で始まるが閉じ忘れた残骸も hints に出る (打ち切り検出補助)。"""
    text = '回答中に <tool_call>{"name":"search","arguments":{"query":"x"}'
    _calls, _cleaned, diagnostics = extract_tool_calls_with_diagnostics(text)
    hints = diagnostics["suspected_unparsed_tool_calls"]
    assert hints, "orphan <tool_call> 残骸を検出すること"
    assert any("<tool_call>" in h or '"name"' in h for h in hints)


def test_diagnostics_empty_when_clean_text() -> None:
    """tool_call らしき痕跡が一切ない通常テキストでは hints は空。"""
    text = "これは普通の日本語の回答文です。検索しなくても答えられます。"
    calls, _cleaned, diagnostics = extract_tool_calls_with_diagnostics(text)
    assert calls == []
    assert diagnostics["suspected_unparsed_tool_calls"] == []
