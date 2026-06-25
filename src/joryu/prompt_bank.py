"""JSONL prompt bank loader と既定値マージ。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from joryu.config import Config
from joryu.io.jsonl import iter_jsonl
from joryu.tools import ToolDefinition, merge_tools, resolve_tool_ids

_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "max_tokens", "repetition_penalty")

_TOOL_USAGE_HINT = (
    "利用可能なツールが提供されています。"
    "不明な事実・数値・最新情報はツールで確認し、その結果を踏まえて回答してください。"
    "ツールを使わずに架空のデータ・出典・URL を作らないでください。"
)


@dataclass
class PromptRow:
    """JSONL 1 行 = 1 プロンプト。`prompt` 以外は任意上書き。"""

    prompt: str
    category: str | None = None
    style_id: str | None = None
    system_prompt: str | None = None
    sampling: dict[str, Any] = field(default_factory=dict)
    tool_ids: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EffectiveSampling:
    """行 + Config を解決した「実際にサンプラーへ渡される」値。"""

    system_prompt: str
    sampling: dict[str, Any]
    category: str | None = None
    style_id: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)


def _parse_row(obj: dict[str, Any]) -> PromptRow:
    if "prompt" not in obj or not isinstance(obj["prompt"], str) or not obj["prompt"].strip():
        raise ValueError("prompt bank row missing required 'prompt' string")
    # mode フィールドは #94 で蒸留側から削除。レガシー JSONL に含まれていても無視する。
    sampling_raw = obj.get("sampling") or {}
    if not isinstance(sampling_raw, dict):
        raise ValueError("sampling must be a JSON object")
    sampling = {k: v for k, v in sampling_raw.items() if k in _SAMPLING_KEYS}
    tool_ids_raw = obj.get("tool_ids") or []
    if not isinstance(tool_ids_raw, list) or not all(isinstance(x, str) for x in tool_ids_raw):
        raise ValueError("tool_ids must be a list of strings")
    tools_raw = obj.get("tools") or []
    if not isinstance(tools_raw, list) or not all(isinstance(x, dict) for x in tools_raw):
        raise ValueError("tools must be a list of objects")
    return PromptRow(
        prompt=obj["prompt"],
        category=obj.get("category"),
        style_id=obj.get("style_id"),
        system_prompt=obj.get("system_prompt"),
        sampling=sampling,
        tool_ids=list(tool_ids_raw),
        tools=list(tools_raw),
    )


def load_prompt_bank(path: str | Path) -> list[PromptRow]:
    """JSONL から PromptRow のリストを返す。空行・JSON 解釈失敗行はスキップ。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"prompt bank not found: {p}")
    rows: list[PromptRow] = []
    for obj in iter_jsonl(p):
        rows.append(_parse_row(obj))
    return rows


def merge_with_defaults(
    row: PromptRow,
    cfg: Config,
    *,
    tools_registry: dict[str, ToolDefinition] | None = None,
) -> EffectiveSampling:
    """PromptRow の上書き値と Config 既定値を畳んで EffectiveSampling を返す。"""
    sampling: dict[str, Any] = {
        "temperature": cfg.model.temperature,
        "top_p": cfg.model.top_p,
        "top_k": cfg.model.top_k,
        "max_tokens": cfg.model.num_predict,
        "repetition_penalty": cfg.model.repetition_penalty,
    }
    for k, v in row.sampling.items():
        sampling[k] = v

    system_prompt = (
        row.system_prompt if row.system_prompt is not None else cfg.distill.system_prompt
    )
    resolved_tools: list[dict[str, Any]] = []
    if row.tool_ids:
        if tools_registry is None:
            raise ValueError("tool_ids 参照には tools_registry が必須")
        resolved = resolve_tool_ids(row.tool_ids, tools_registry)
        resolved_tools = [t.to_openai_schema() for t in resolved]
    if row.tools:
        resolved_tools = merge_tools(resolved_tools, row.tools)
    if resolved_tools:
        base = system_prompt.rstrip()
        system_prompt = f"{base}\n\n{_TOOL_USAGE_HINT}" if base else _TOOL_USAGE_HINT
    return EffectiveSampling(
        system_prompt=system_prompt,
        sampling=sampling,
        category=row.category,
        style_id=row.style_id,
        tools=resolved_tools,
    )
