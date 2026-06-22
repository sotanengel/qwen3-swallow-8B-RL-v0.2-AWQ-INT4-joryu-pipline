"""JSONL prompt bank loader と既定値マージ。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from joryu.config import Config, Mode
from joryu.io.jsonl import iter_jsonl

_VALID_MODES = ("thinking", "nothinking")
_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "max_tokens", "repetition_penalty")


@dataclass
class PromptRow:
    """JSONL 1 行 = 1 プロンプト。`prompt` 以外は任意上書き。"""

    prompt: str
    category: str | None = None
    style_id: str | None = None
    mode: Mode | None = None
    system_prompt: str | None = None
    sampling: dict[str, Any] = field(default_factory=dict)


@dataclass
class EffectiveSampling:
    """行 + Config を解決した「実際にサンプラーへ渡される」値。"""

    mode: Mode
    system_prompt: str
    sampling: dict[str, Any]
    category: str | None = None
    style_id: str | None = None


def _parse_row(obj: dict[str, Any]) -> PromptRow:
    if "prompt" not in obj or not isinstance(obj["prompt"], str) or not obj["prompt"].strip():
        raise ValueError("prompt bank row missing required 'prompt' string")
    mode = obj.get("mode")
    if mode is not None and mode not in _VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {_VALID_MODES}")
    sampling_raw = obj.get("sampling") or {}
    if not isinstance(sampling_raw, dict):
        raise ValueError("sampling must be a JSON object")
    sampling = {k: v for k, v in sampling_raw.items() if k in _SAMPLING_KEYS}
    return PromptRow(
        prompt=obj["prompt"],
        category=obj.get("category"),
        style_id=obj.get("style_id"),
        mode=mode,
        system_prompt=obj.get("system_prompt"),
        sampling=sampling,
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


def merge_with_defaults(row: PromptRow, cfg: Config) -> EffectiveSampling:
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
    return EffectiveSampling(
        mode=row.mode or cfg.model.mode,
        system_prompt=system_prompt,
        sampling=sampling,
        category=row.category,
        style_id=row.style_id,
    )
