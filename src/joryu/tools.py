"""ツール定義 (tools.yaml) の読み込みと OpenAI schema 解決。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from joryu.yaml_util import load_yaml_mapping


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def load_tools(path: str | Path) -> dict[str, ToolDefinition]:
    """tools.yaml からツール辞書を読み込む。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"tools file not found: {p}")
    raw = load_yaml_mapping(p)
    tools_raw = raw.get("tools") or {}
    if not isinstance(tools_raw, dict):
        raise ValueError("tools.yaml: 'tools' must be a mapping")
    out: dict[str, ToolDefinition] = {}
    for tool_id, body in tools_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"tools.yaml: tool {tool_id!r} must be a mapping")
        description = body.get("description")
        parameters = body.get("parameters")
        if not description or not isinstance(description, str):
            raise ValueError(f"tools.yaml: tool {tool_id!r} missing 'description'")
        if not isinstance(parameters, dict):
            raise ValueError(f"tools.yaml: tool {tool_id!r} missing 'parameters'")
        out[str(tool_id)] = ToolDefinition(
            name=str(tool_id),
            description=description.strip(),
            parameters=parameters,
        )
    return out


def resolve_tool_ids(ids: list[str], tools: dict[str, ToolDefinition]) -> list[ToolDefinition]:
    """CLI / JSONL で指定された tool ID を解決。未知 ID は ValueError。"""
    resolved: list[ToolDefinition] = []
    for tool_id in ids:
        if tool_id not in tools:
            known = ", ".join(sorted(tools))
            raise ValueError(f"unknown tool {tool_id!r}; known tools: {known}")
        resolved.append(tools[tool_id])
    return resolved


def _normalize_adhoc_tool(entry: dict[str, Any]) -> dict[str, Any]:
    """ad-hoc 直書きを OpenAI function schema に正規化。"""
    if entry.get("type") == "function" and isinstance(entry.get("function"), dict):
        return entry
    name = entry.get("name")
    description = entry.get("description")
    parameters = entry.get("parameters")
    if not name or not isinstance(name, str):
        raise ValueError("ad-hoc tool missing 'name'")
    if not description or not isinstance(description, str):
        raise ValueError(f"ad-hoc tool {name!r} missing 'description'")
    if not isinstance(parameters, dict):
        raise ValueError(f"ad-hoc tool {name!r} missing 'parameters'")
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def merge_tools(
    resolved: list[dict[str, Any]],
    adhoc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """ad-hoc は同名衝突時に勝つ。返却は OpenAI schema 配列。"""
    by_name: dict[str, dict[str, Any]] = {}
    for schema in resolved:
        fn = schema.get("function") or {}
        name = fn.get("name")
        if isinstance(name, str):
            by_name[name] = schema
    for entry in adhoc:
        schema = _normalize_adhoc_tool(entry)
        fn = schema.get("function") or {}
        name = fn.get("name")
        if isinstance(name, str):
            by_name[name] = schema
    return list(by_name.values())
