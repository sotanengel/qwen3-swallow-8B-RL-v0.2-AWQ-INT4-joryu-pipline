"""JSONL prompt bank loader と既定値マージ。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from joryu.config import Config
from joryu.io.jsonl import iter_jsonl
from joryu.tools import ToolDefinition, merge_tools, resolve_tool_ids

logger = logging.getLogger(__name__)

_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "max_tokens", "repetition_penalty")

_TOOL_USAGE_HINT = (
    "利用可能なツールが提供されています。"
    "不明な事実・数値・最新情報はツールで確認し、その結果を踏まえて回答してください。"
    "ツールを使わずに架空のデータ・出典・URL を作らないでください。"
)


class PromptRow(BaseModel):
    """JSONL 1 行 = 1 プロンプト。`prompt` 以外は任意上書き。"""

    model_config = ConfigDict(extra="ignore")

    prompt: str
    category: str | None = None
    style_id: str | None = None
    system_prompt: str | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)
    tool_ids: list[str] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("prompt")
    @classmethod
    def _prompt_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt bank row missing required 'prompt' string")
        return stripped

    @field_validator("sampling", mode="before")
    @classmethod
    def _normalize_sampling(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("sampling must be a JSON object")
        return {k: v for k, v in value.items() if k in _SAMPLING_KEYS}

    @field_validator("tool_ids", mode="before")
    @classmethod
    def _normalize_tool_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError("tool_ids must be a list of strings")
        return list(value)

    @field_validator("tools", mode="before")
    @classmethod
    def _normalize_tools(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
            raise ValueError("tools must be a list of objects")
        return list(value)


@dataclass
class EffectiveSampling:
    """行 + Config を解決した「実際にサンプラーへ渡される」値。"""

    system_prompt: str
    sampling: dict[str, Any]
    category: str | None = None
    style_id: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)


def load_prompt_bank(path: str | Path) -> list[PromptRow]:
    """JSONL から PromptRow のリストを返す。空行・JSON 解釈失敗行はスキップ。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"prompt bank not found: {p}")
    rows: list[PromptRow] = []
    for obj in iter_jsonl(p, logger=logger, log_prefix="prompt bank"):
        try:
            rows.append(PromptRow.model_validate(obj))
        except Exception as exc:
            logger.warning("prompt bank skip invalid row: %s", exc)
    return rows


def format_tool_usage_hint(tool_defs: list[ToolDefinition]) -> str:
    """tools 解決後の system_prompt 追記文を組み立てる (#112)。"""
    if not tool_defs:
        return _TOOL_USAGE_HINT
    if not any(t.invocation_rule for t in tool_defs):
        return _TOOL_USAGE_HINT
    lines = ["利用可能なツール:"]
    for tool in tool_defs:
        rule = tool.invocation_rule or tool.description
        lines.append(f"- {tool.name}: {rule}")
    lines.append(
        "ツールを使わずに架空のデータ・出典・URL を作らないでください。"
        "推測でツールを使ったかのように装ってはいけません。"
    )
    return "\n".join(lines)


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
    resolved_tool_defs: list[ToolDefinition] = []
    if row.tool_ids:
        if tools_registry is None:
            raise ValueError("tool_ids 参照には tools_registry が必須")
        resolved_tool_defs = resolve_tool_ids(row.tool_ids, tools_registry)
        resolved_tools = [t.to_openai_schema() for t in resolved_tool_defs]
    if row.tools:
        resolved_tools = merge_tools(resolved_tools, row.tools)
    if resolved_tools and "repetition_penalty" not in row.sampling:
        sampling["repetition_penalty"] = cfg.distill.tools_repetition_penalty
    # tool hint は variants.expand_variants → build_system_prompt で style より前に付与
    return EffectiveSampling(
        system_prompt=system_prompt,
        sampling=sampling,
        category=row.category,
        style_id=row.style_id,
        tools=resolved_tools,
    )
