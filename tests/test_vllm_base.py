"""HttpVllmBase と ToolCallParser の単体テスト (#256)。"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

from joryu.vllm.base import HttpVllmBase
from joryu.vllm.tool_parser import (
    BareJsonToolCallParser,
    CompositeToolCallParser,
    FenceToolCallParser,
    TagToolCallParser,
)


def test_http_vllm_base_normalizes_url() -> None:
    base = HttpVllmBase("http://localhost:8100/v1", model="m")
    assert base.normalized_base_url() == "http://localhost:8100"


def test_http_vllm_base_post_json_with_retry_success() -> None:
    base = HttpVllmBase("http://localhost:8100", model="m", timeout_s=5.0)
    payload = {"model": "m", "messages": []}
    response_body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as urlopen:
        data = base.post_json_with_retry("/v1/chat/completions", payload)

    assert data["choices"][0]["message"]["content"] == "ok"
    urlopen.assert_called_once()


def test_http_vllm_base_post_json_retries_on_url_error() -> None:
    base = HttpVllmBase(
        "http://localhost:8100",
        model="m",
        retry_attempts=2,
    )
    payload = {"model": "m"}
    response_body = json.dumps({"ok": True}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    side_effects = [urllib.error.URLError("conn"), mock_resp]
    with (
        patch("urllib.request.urlopen", side_effect=side_effects) as urlopen,
        patch("time.sleep"),
    ):
        data = base.post_json_with_retry("/v1/chat/completions", payload)

    assert data == {"ok": True}
    assert urlopen.call_count == 2


def test_tag_tool_call_parser_extracts_tag_block() -> None:
    text = 'prefix <tool_call>{"name": "search", "arguments": {"q": "x"}}</tool_call> suffix'
    parser = TagToolCallParser()
    calls, spans = parser.parse(text)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert len(spans) == 1


def test_fence_tool_call_parser_extracts_json_fence() -> None:
    text = 'answer ```json\n{"name": "fetch", "arguments": {"url": "https://x"}}\n``` tail'
    parser = FenceToolCallParser()
    calls, spans = parser.parse(text)
    assert len(calls) == 1
    assert calls[0].name == "fetch"
    assert len(spans) == 1


def test_bare_json_parser_requires_known_names() -> None:
    text = '{"name": "search", "arguments": {"q": "y"}}'
    parser = BareJsonToolCallParser()
    calls_none, spans_none = parser.parse(text, known_tool_names=None)
    assert calls_none == []
    assert spans_none == []
    calls, spans = parser.parse(text, known_tool_names={"search"})
    assert len(calls) == 1
    assert len(spans) == 1


def test_composite_parser_merges_strategies() -> None:
    text = (
        '<tool_call>{"name": "a", "arguments": {}}</tool_call> '
        '```json\n{"name": "b", "arguments": {}}\n```'
    )
    parser = CompositeToolCallParser()
    calls, _ = parser.parse(text)
    names = {c.name for c in calls}
    assert names == {"a", "b"}
