"""JSONL レコードから chat_template 入力を再構築するユーティリティ。"""

from __future__ import annotations

from typing import Any


def rebuild_chat_template_inputs(record: dict[str, Any]) -> dict[str, Any]:
    """レコード内 tools のみで apply_chat_template に渡す inputs を組み立てる。"""
    tools = record.get("tools") or []
    if not isinstance(tools, list):
        raise ValueError("tools must be a list")
    for schema in tools:
        if not isinstance(schema, dict):
            raise ValueError("each tool schema must be an object")
        if schema.get("type") != "function":
            raise ValueError("tool schema must have type=function")
        fn = schema.get("function")
        if not isinstance(fn, dict) or not isinstance(fn.get("name"), str):
            raise ValueError("tool schema missing function.name")
    return {
        "messages": [
            {"role": "system", "content": str(record.get("system_prompt") or "")},
            {"role": "user", "content": str(record.get("prompt") or "")},
        ],
        "tools": tools,
        "add_generation_prompt": True,
    }
