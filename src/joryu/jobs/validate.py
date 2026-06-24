"""ジョブ spec の検証。"""

from __future__ import annotations

from pathlib import Path

from joryu.cli.distill import parse_duration
from joryu.config import load_config
from joryu.jobs.models import CurateJobSpec, DistillJobSpec
from joryu.preflight import jsonl_has_content, resolve_distill_jsonl
from joryu.styles import load_styles, resolve_style_ids
from joryu.tools import load_tools
from joryu.variants import parse_comma_list, parse_float_list, parse_modes


def validate_job_spec(spec: DistillJobSpec, *, repo_root: Path | None = None) -> None:
    """DistillJobSpec を joryu-distill と同じ規則で検証。失敗時 ValueError。"""
    if spec.count < 0:
        raise ValueError("count must be >= 0")

    if spec.duration:
        try:
            parse_duration(spec.duration)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    if spec.mode is not None:
        try:
            parse_modes(spec.mode)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    cfg_path = Path(spec.config)
    if not cfg_path.is_absolute() and repo_root is not None:
        cfg_path = repo_root / cfg_path
    try:
        cfg = load_config(cfg_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(str(exc)) from exc

    if spec.tool_ids:
        tools_path = cfg_path.parent / cfg.distill.tools_file
        if not tools_path.is_absolute():
            tools_path = cfg_path.parent / tools_path
        reg = load_tools(tools_path)
        from joryu.tools import resolve_tool_ids

        resolve_tool_ids(spec.tool_ids, reg)

    if spec.max_turns is not None and spec.max_turns < 1:
        raise ValueError("max_turns must be >= 1")

    if spec.temperature:
        parse_float_list(spec.temperature, min_val=0.5, max_val=1.0, name="temperature")
    if spec.top_p:
        parse_float_list(spec.top_p, min_val=0.8, max_val=0.95, name="top_p")

    if spec.style:
        styles_path = cfg_path.parent / cfg.distill.styles_file
        styles = load_styles(styles_path)
        resolve_style_ids(spec.style, styles)
        parse_comma_list(",".join(spec.style))


def validate_curate_job_spec(spec: CurateJobSpec, *, repo_root: Path | None = None) -> None:
    """CurateJobSpec を検証。失敗時 ValueError。"""
    cfg_path = Path(spec.config)
    if not cfg_path.is_absolute() and repo_root is not None:
        cfg_path = repo_root / cfg_path
    try:
        load_config(cfg_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(str(exc)) from exc

    if spec.threshold is not None and not (0.0 <= spec.threshold <= 1.0):
        raise ValueError("threshold must be between 0.0 and 1.0")

    if repo_root is not None:
        jsonl = resolve_distill_jsonl(repo_root)
        if not jsonl_has_content(jsonl):
            raise ValueError(f"distill output is empty or missing: {jsonl}")
