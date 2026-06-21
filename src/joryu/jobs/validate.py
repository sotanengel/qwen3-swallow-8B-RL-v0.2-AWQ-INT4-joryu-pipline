"""ジョブ spec の検証。"""

from __future__ import annotations

from pathlib import Path

from joryu.cli.distill import parse_duration
from joryu.config import load_config
from joryu.jobs.models import DistillJobSpec
from joryu.styles import load_styles, resolve_style_ids
from joryu.variants import parse_comma_list, parse_float_list


def validate_job_spec(spec: DistillJobSpec, *, repo_root: Path | None = None) -> None:
    """DistillJobSpec を joryu-distill と同じ規則で検証。失敗時 ValueError。"""
    from pathlib import Path

    if spec.count < 0:
        raise ValueError("count must be >= 0")

    if spec.duration:
        try:
            parse_duration(spec.duration)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    if spec.mode is not None and spec.mode not in ("thinking", "nothinking"):
        raise ValueError("mode must be 'thinking' or 'nothinking'")

    cfg_path = Path(spec.config)
    if not cfg_path.is_absolute() and repo_root is not None:
        cfg_path = repo_root / cfg_path
    try:
        cfg = load_config(cfg_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(str(exc)) from exc

    if spec.style:
        styles_path = cfg_path.parent / cfg.distill.styles_file
        styles = load_styles(styles_path)
        resolve_style_ids(spec.style, styles)

    if spec.temperature:
        parse_float_list(spec.temperature, min_val=0.5, max_val=1.0, name="temperature")
    if spec.top_p:
        parse_float_list(spec.top_p, min_val=0.8, max_val=0.95, name="top_p")

    if spec.style:
        parse_comma_list(",".join(spec.style))
