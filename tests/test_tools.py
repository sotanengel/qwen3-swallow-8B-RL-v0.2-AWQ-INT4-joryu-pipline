"""tools.py: tools.yaml 読み込みと schema 解決。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.tools import ToolDefinition, load_tools, merge_tools, resolve_tool_ids


def test_load_tools_reads_repo_tools_yaml() -> None:
    reg = load_tools("tools.yaml")
    assert set(reg) == {"search", "calc", "fetch_url"}


def test_resolve_tool_ids_returns_two() -> None:
    reg = load_tools("tools.yaml")
    resolved = resolve_tool_ids(["search", "calc"], reg)
    assert len(resolved) == 2
    assert resolved[0].name == "search"


def test_resolve_tool_ids_unknown_raises() -> None:
    reg = load_tools("tools.yaml")
    with pytest.raises(ValueError, match="unknown tool"):
        resolve_tool_ids(["missing"], reg)


def test_to_openai_schema_shape() -> None:
    tool = ToolDefinition(
        name="search",
        description="search web",
        parameters={"type": "object", "properties": {}},
    )
    schema = tool.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search"
    assert schema["function"]["description"] == "search web"


def test_merge_tools_adhoc_wins_on_name_collision() -> None:
    reg = load_tools("tools.yaml")
    resolved = [t.to_openai_schema() for t in resolve_tool_ids(["search"], reg)]
    adhoc = [
        {
            "name": "search",
            "description": "override",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    merged = merge_tools(resolved, adhoc)
    assert len(merged) == 1
    assert merged[0]["function"]["description"] == "override"


def test_load_tools_reads_invocation_rule(tmp_path: Path) -> None:
    p = tmp_path / "tools.yaml"
    p.write_text(
        "tools:\n  search:\n    description: d\n"
        "    invocation_rule: 事実確認時は必ず呼ぶ\n"
        "    parameters:\n      type: object\n      properties: {}\n",
        encoding="utf-8",
    )
    reg = load_tools(p)
    assert reg["search"].invocation_rule == "事実確認時は必ず呼ぶ"
    with pytest.raises(FileNotFoundError):
        load_tools(tmp_path / "missing.yaml")
