"""アーキテクチャ層のガードテスト（依存関係の再発防止, epic #405）。

`src/joryu` 配下のモジュール top-level import のみを対象に依存グラフを構築し、
以下を検証する:

- Test A: モジュール単位で相互依存（循環）が発生していないこと。
- Test B: コンポーネント単位（`joryu.xxx` の先頭2セグメント）で相互依存が
  発生していないこと。
- Test C: エントリ層（`joryu.cli` / `joryu.api`）が下位層から import
  されていないこと。

対象となるのは module top-level の実行時 import のみ。関数・メソッド・クラス
本体内で行われる遅延 import は、本リポジトリで循環依存を断ち切るための正式な
パターンとして許容されており、このガードの対象外とする
（`if TYPE_CHECKING:` ブロックも型検査専用のため同様に対象外）。

新たな循環・違反を許可リストへ追加することは意図的な設計判断としてあり得るが、
許可リスト（`ALLOWED_MODULE_CYCLES` / `ALLOWED_COMPONENT_CYCLES` /
`ALLOWED_ENTRY_IMPORTS`）は縮小方向にのみ更新すること
（既存の許可は #409 で解消予定）。
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
_PACKAGE_ROOT = _SRC_ROOT / "joryu"
_PACKAGE_NAME = "joryu"

# ---------------------------------------------------------------------------
# 許可リスト（縮小方向にのみ更新すること）
# ---------------------------------------------------------------------------

#: モジュール単位の循環依存の許可リスト。現状は空（循環なし）。
ALLOWED_MODULE_CYCLES: set[frozenset[str]] = set()

#: コンポーネント単位（先頭2セグメント）の循環依存の許可リスト。
#: 中心となるのは joryu.cli.distill -> joryu.jobs.models と
#: joryu.jobs.validate -> joryu.cli.distill の相互依存（joryu.cli <-> joryu.jobs）。
#: さらに joryu.cli.down / joryu.cli.up -> joryu.orchestrator.profile、
#: joryu.orchestrator.required -> joryu.jobs.models の依存が連鎖し、
#: joryu.cli / joryu.jobs / joryu.orchestrator の3コンポーネントが
#: 強連結成分を形成している。
#: #409 (PR3) で joryu.jobs.validate -> joryu.cli.distill を解消し、
#: このエントリを削除する予定。
ALLOWED_COMPONENT_CYCLES: set[frozenset[str]] = {
    frozenset({"joryu.cli", "joryu.jobs", "joryu.orchestrator"}),
}

#: エントリ層（joryu.cli / joryu.api）を下位層から import している箇所の許可リスト。
#: #409 (PR3) で joryu.jobs.validate から joryu.cli.distill への依存を解消し、
#: このエントリを削除する予定。
ALLOWED_ENTRY_IMPORTS: set[tuple[str, str]] = {
    ("joryu.jobs.validate", "joryu.cli.distill"),
}

# ---------------------------------------------------------------------------
# モジュール一覧・import グラフの構築
# ---------------------------------------------------------------------------


def _module_name_for_path(path: Path) -> str:
    """ファイルパスから `joryu.xxx.yyy` 形式のモジュール名を求める。"""
    rel = path.relative_to(_SRC_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _iter_source_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def _all_module_names() -> set[str]:
    """`joryu.*` の全モジュール名（パッケージ含む）の集合。"""
    names: set[str] = set()
    for path in _iter_source_files():
        names.add(_module_name_for_path(path))
    return names


def _is_type_checking_test(test: ast.expr) -> bool:
    """`if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:` の条件式かどうか判定する。"""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _iter_runtime_top_level_stmts(tree: ast.Module) -> list[ast.stmt]:
    """module top-level の実行時文を返す（`if TYPE_CHECKING:` の中身は除く）。

    top-level の `if` 文は再帰的に中身を展開するが、TYPE_CHECKING ブロックの
    みは実行時 import ではないためスキップする。`else` 節や他の分岐は展開する。
    """
    result: list[ast.stmt] = []
    for stmt in tree.body:
        result.extend(_expand_stmt(stmt))
    return result


def _expand_stmt(stmt: ast.stmt) -> list[ast.stmt]:
    if isinstance(stmt, ast.If):
        expanded: list[ast.stmt] = []
        if not _is_type_checking_test(stmt.test):
            for sub in stmt.body:
                expanded.extend(_expand_stmt(sub))
        for sub in stmt.orelse:
            expanded.extend(_expand_stmt(sub))
        return expanded
    return [stmt]


def _resolve_module_target(module_names: set[str], dotted: str) -> str | None:
    """import 対象のドット区切り名を既知の `joryu.*` モジュール名へ解決する。

    `from joryu.a import b` のような場合、`joryu.a.b` がモジュールとして
    実在すればそちらを、なければ `joryu.a` を返す（`b` が関数/クラス等の場合）。
    """
    if dotted in module_names:
        return dotted
    return None


def _resolve_import_from(
    *,
    module_names: set[str],
    current_module: str,
    node: ast.ImportFrom,
) -> list[str]:
    """`from X import a, b` 文から依存先モジュール名のリストを求める。"""
    targets: list[str] = []

    if node.level and node.level > 0:
        # 相対 import: current_module の位置を基準にベースモジュールを求める。
        current_parts = current_module.split(".")
        # current_module がパッケージ(__init__)かモジュールファイルかで
        # 基準となる「自分がいるパッケージ」の深さが変わる。
        is_package = (_PACKAGE_ROOT / Path(*current_parts[1:]) / "__init__.py").exists()
        if is_package:
            package_parts = current_parts
        else:
            package_parts = current_parts[:-1]
        # level=1 は自パッケージ、level=2 は親パッケージ、...
        base_parts = package_parts[: len(package_parts) - (node.level - 1)]
        if node.module:
            base_parts = base_parts + node.module.split(".")
        base = ".".join(base_parts)
    else:
        if node.module is None or not (
            node.module == _PACKAGE_NAME or node.module.startswith(_PACKAGE_NAME + ".")
        ):
            return targets
        base = node.module

    if base == _PACKAGE_NAME or base.startswith(_PACKAGE_NAME + "."):
        # base 自体がモジュールであれば直接対象。
        resolved = _resolve_module_target(module_names, base)
        if resolved is not None:
            targets.append(resolved)
        # 各 alias が `base.name` というサブモジュールを指す可能性もチェックする。
        for alias in node.names:
            if alias.name == "*":
                continue
            candidate = f"{base}.{alias.name}"
            resolved_candidate = _resolve_module_target(module_names, candidate)
            if resolved_candidate is not None:
                targets.append(resolved_candidate)
        if resolved is None and not targets:
            # base 自体も candidate も未知のモジュール名だった場合は無視する
            # （joryu パッケージ外、あるいは解決不能な動的 import）。
            return []
    return targets


def _resolve_import(
    *,
    module_names: set[str],
    node: ast.Import,
) -> list[str]:
    targets: list[str] = []
    for alias in node.names:
        name = alias.name
        if name == _PACKAGE_NAME or name.startswith(_PACKAGE_NAME + "."):
            resolved = _resolve_module_target(module_names, name)
            if resolved is not None:
                targets.append(resolved)
    return targets


def _build_module_graph() -> dict[str, set[str]]:
    """`joryu.*` モジュール間の top-level import 依存グラフを構築する。"""
    module_names = _all_module_names()
    graph: dict[str, set[str]] = {name: set() for name in module_names}

    for path in _iter_source_files():
        current_module = _module_name_for_path(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        for stmt in _iter_runtime_top_level_stmts(tree):
            if isinstance(stmt, ast.Import):
                targets = _resolve_import(module_names=module_names, node=stmt)
            elif isinstance(stmt, ast.ImportFrom):
                targets = _resolve_import_from(
                    module_names=module_names,
                    current_module=current_module,
                    node=stmt,
                )
            else:
                continue

            for target in targets:
                if target != current_module:
                    graph[current_module].add(target)

    return graph


# ---------------------------------------------------------------------------
# Tarjan 法による強連結成分（SCC）分解
# ---------------------------------------------------------------------------


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    """Tarjan 法により強連結成分（SCC）の一覧を求める（自己ループは含めない）。"""
    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[set[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index_counter
        indices[node] = index_counter
        lowlink[node] = index_counter
        index_counter += 1
        stack.append(node)
        on_stack.add(node)

        for successor in graph.get(node, ()):
            if successor not in indices:
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif successor in on_stack:
                lowlink[node] = min(lowlink[node], indices[successor])

        if lowlink[node] == indices[node]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.add(member)
                if member == node:
                    break
            result.append(component)

    for node in graph:
        if node not in indices:
            strongconnect(node)

    return result


def _component_name(module_name: str) -> str:
    """モジュール名からコンポーネント名（先頭2セグメント）を求める。"""
    parts = module_name.split(".")
    if len(parts) < 2:
        return module_name
    return ".".join(parts[:2])


def _build_component_graph(module_graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """モジュールグラフをコンポーネット単位（先頭2セグメント）へ集約する（自己エッジは除外）。"""
    component_graph: dict[str, set[str]] = defaultdict(set)
    for module_name in module_graph:
        component_graph.setdefault(_component_name(module_name), set())

    for source, targets in module_graph.items():
        source_component = _component_name(source)
        for target in targets:
            target_component = _component_name(target)
            if source_component != target_component:
                component_graph[source_component].add(target_component)

    return dict(component_graph)


def _format_cycle(cycle: frozenset[str]) -> str:
    return "{" + ", ".join(sorted(cycle)) + "}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_module_level_import_cycles() -> None:
    """Test A: モジュール単位の top-level import で循環依存が無いこと。"""
    graph = _build_module_graph()
    sccs = _strongly_connected_components(graph)
    detected_cycles = {frozenset(scc) for scc in sccs if len(scc) > 1}

    unexpected_cycles = detected_cycles - ALLOWED_MODULE_CYCLES
    assert not unexpected_cycles, (
        "モジュール単位の循環依存が検出された（許可リスト外）:\n"
        + "\n".join(f"  - {_format_cycle(cycle)}" for cycle in sorted(unexpected_cycles, key=str))
        + "\n関数内 import による遅延解決を検討するか、ALLOWED_MODULE_CYCLES に"
        " 意図的な許可として追加すること。"
    )

    # 許可リストが既に不要になった場合に気付けるよう、存在しない許可は検出する。
    stale_allowances = ALLOWED_MODULE_CYCLES - detected_cycles
    assert not stale_allowances, (
        "ALLOWED_MODULE_CYCLES に実際には存在しない循環が登録されている"
        "（許可リストは縮小方向にのみ更新すること）:\n"
        + "\n".join(f"  - {_format_cycle(cycle)}" for cycle in sorted(stale_allowances, key=str))
    )


def test_no_component_level_import_cycles() -> None:
    """Test B: コンポーネント単位（先頭2セグメント）で循環依存が無いこと。"""
    module_graph = _build_module_graph()
    component_graph = _build_component_graph(module_graph)
    sccs = _strongly_connected_components(component_graph)
    detected_cycles = {frozenset(scc) for scc in sccs if len(scc) > 1}

    unexpected_cycles = detected_cycles - ALLOWED_COMPONENT_CYCLES
    assert not unexpected_cycles, (
        "コンポーネント単位の循環依存が検出された（許可リスト外）:\n"
        + "\n".join(f"  - {_format_cycle(cycle)}" for cycle in sorted(unexpected_cycles, key=str))
        + "\nコンポーネント間の依存方向を見直すか、ALLOWED_COMPONENT_CYCLES に"
        " 意図的な許可として追加すること。"
    )

    stale_allowances = ALLOWED_COMPONENT_CYCLES - detected_cycles
    assert not stale_allowances, (
        "ALLOWED_COMPONENT_CYCLES に実際には存在しない循環が登録されている"
        "（許可リストは縮小方向にのみ更新すること）:\n"
        + "\n".join(f"  - {_format_cycle(cycle)}" for cycle in sorted(stale_allowances, key=str))
    )


def test_no_lower_layer_imports_entry_layer() -> None:
    """Test C: エントリ層（joryu.cli / joryu.api）が下位層から import されていないこと。"""
    module_graph = _build_module_graph()

    def _is_entry_layer(module_name: str) -> bool:
        return (
            module_name == "joryu.cli"
            or module_name == "joryu.api"
            or module_name.startswith("joryu.cli.")
            or module_name.startswith("joryu.api.")
        )

    detected_edges: set[tuple[str, str]] = set()
    for source, targets in module_graph.items():
        if _is_entry_layer(source):
            # entry 層内部（joryu.cli.* 同士 / joryu.api.* 同士）の import は対象外。
            continue
        for target in targets:
            if _is_entry_layer(target):
                detected_edges.add((source, target))

    unexpected_edges = detected_edges - ALLOWED_ENTRY_IMPORTS
    assert not unexpected_edges, (
        "下位層モジュールが entry 層（joryu.cli / joryu.api）を import している"
        "（許可リスト外）:\n"
        + "\n".join(f"  - {src} -> {dst}" for src, dst in sorted(unexpected_edges))
        + "\nentry 層はエントリポイント専用とし、下位層から依存しない設計へ修正するか、"
        " ALLOWED_ENTRY_IMPORTS に意図的な許可として追加すること。"
    )

    stale_allowances = ALLOWED_ENTRY_IMPORTS - detected_edges
    assert not stale_allowances, (
        "ALLOWED_ENTRY_IMPORTS に実際には存在しない依存が登録されている"
        "（許可リストは縮小方向にのみ更新すること）:\n"
        + "\n".join(f"  - {src} -> {dst}" for src, dst in sorted(stale_allowances))
    )
