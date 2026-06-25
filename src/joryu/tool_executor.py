"""ツール呼び出しのローカル実行 (蒸留用スタブ / 純関数レジストリ)。"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any, Protocol

from joryu.tool_calls import ParsedToolCall

_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SAFE_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ToolExecutor(Protocol):
    def run(self, call: ParsedToolCall) -> str: ...


class StubToolExecutor:
    """テスト/スモーク用。tool name と arguments を mock 応答で返す。"""

    def __init__(self, fixed: dict[str, str] | None = None) -> None:
        self._fixed = fixed or {}

    def run(self, call: ParsedToolCall) -> str:
        if call.name in self._fixed:
            return self._fixed[call.name]
        return f"stub:{call.name}:{call.arguments}"


def _eval_arithmetic(expression: str) -> str:
    node = ast.parse(expression, mode="eval")

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _SAFE_UNARYOPS:
            return _SAFE_UNARYOPS[type(n.op)](_eval(n.operand))
        if isinstance(n, ast.BinOp) and type(n.op) in _SAFE_BINOPS:
            return _SAFE_BINOPS[type(n.op)](_eval(n.left), _eval(n.right))
        raise ValueError(f"unsupported expression: {expression!r}")

    result = _eval(node)
    if result.is_integer():
        return str(int(result))
    return str(result)


class RegistryToolExecutor:
    """name → callable のレジストリ。"""

    def __init__(self) -> None:
        self._fns: dict[str, Callable[[dict[str, Any]], str]] = {}

    def register(self, name: str, fn: Callable[[dict[str, Any]], str]) -> None:
        self._fns[name] = fn

    def run(self, call: ParsedToolCall) -> str:
        if call.name not in self._fns:
            raise KeyError(f"unknown tool: {call.name!r}")
        return self._fns[call.name](call.arguments)


def _calc_fn(arguments: dict[str, Any]) -> str:
    expression = arguments.get("expression")
    if not isinstance(expression, str):
        raise ValueError("calc requires string 'expression'")
    return _eval_arithmetic(expression)


def _search_fn(arguments: dict[str, Any]) -> str:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("search requires string 'query'")
    top_k = arguments.get("top_k", 5)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 5
    lines = [f"[search results for {query!r}, top_k={top_k}]"]
    for i in range(1, min(top_k, 5) + 1):
        lines.append(
            f"{i}. snippet: 「{query}」に関する参考情報 (synthetic result #{i} for distillation)"
        )
    return "\n".join(lines)


def _fetch_url_fn(arguments: dict[str, Any]) -> str:
    url = arguments.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("fetch_url requires string 'url'")
    return (
        f"[page content from {url}]\n"
        f"Title: サンプルページ ({url})\n"
        "Body: この URL から取得した本文の synthetic スタブです。"
        "蒸留用に決定論的なテキストを返しています。"
    )


def build_default_executor() -> RegistryToolExecutor:
    """既定登録: calc + search/fetch_url の決定論的スタブ。"""
    executor = RegistryToolExecutor()
    executor.register("calc", _calc_fn)
    executor.register("search", _search_fn)
    executor.register("fetch_url", _fetch_url_fn)
    return executor
