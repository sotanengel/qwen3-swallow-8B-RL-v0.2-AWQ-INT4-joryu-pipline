"""ジョブ spec の検証。"""

from __future__ import annotations

from pathlib import Path

from joryu.cli.distill import parse_duration
from joryu.config import load_config
from joryu.jobs.models import CurateJobSpec, DistillJobSpec, SeedGenJobSpec
from joryu.preflight import jsonl_has_content, resolve_distill_jsonl
from joryu.styles import load_styles, resolve_style_ids
from joryu.tools import load_tools
from joryu.variants import parse_comma_list, parse_float_list


def validate_job_spec(spec: DistillJobSpec, *, repo_root: Path | None = None) -> None:
    """DistillJobSpec を joryu-distill と同じ規則で検証。失敗時 ValueError。"""
    if spec.count < 0:
        raise ValueError("count must be >= 0")

    if spec.duration:
        try:
            parse_duration(spec.duration)
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

    if repo_root is not None and not (spec.screening and spec.prompt_bank):
        jsonl = resolve_distill_jsonl(repo_root)
        if not jsonl_has_content(jsonl):
            raise ValueError(f"distill output is empty or missing: {jsonl}")

    if spec.screening and spec.prompt_bank and not spec.src and repo_root is not None:
        cfg_path = Path(spec.config)
        if not cfg_path.is_absolute():
            cfg_path = repo_root / cfg_path
        cfg = load_config(cfg_path)
        bank = repo_root / cfg.distill.prompt_bank
        if not bank.is_file():
            raise ValueError(f"prompt bank not found: {bank}")


def validate_seed_gen_job_spec(spec: SeedGenJobSpec, *, repo_root: Path | None = None) -> None:
    """SeedGenJobSpec を検証。失敗時 ValueError。"""
    if spec.target_total <= 0:
        raise ValueError("target_total must be positive")
    if not (0.0 < spec.sim_threshold <= 1.0):
        raise ValueError("sim_threshold must be in (0, 1]")
    if spec.batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if repo_root is not None and spec.domains_config:
        path = Path(spec.domains_config)
        if not path.is_absolute():
            path = repo_root / path
        if not path.is_file():
            from joryu.seed_gen.config import DEFAULT_DOMAINS_REL, resolve_domains_config_path

            try:
                resolve_domains_config_path(repo_root, spec.domains_config or DEFAULT_DOMAINS_REL)
            except FileNotFoundError as exc:
                raise ValueError(str(exc)) from exc
