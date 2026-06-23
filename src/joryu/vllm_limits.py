"""vLLM VRAM プローブ結果の読み込みと設定クランプ。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROBE_CANDIDATES: tuple[tuple[int, int], ...] = (
    (2048, 1024),
    (1536, 768),
    (1024, 640),
    (768, 512),
    (512, 384),
)


@dataclass(frozen=True)
class VllmLimits:
    num_ctx: int
    num_predict: int


def load_probe_limits(path: str | Path | None) -> VllmLimits | None:
    """プローブ JSON から実効上限を読み込む。存在しなければ None。"""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[vllm_limits] failed to read %s: %s", p, exc)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return VllmLimits(num_ctx=int(raw["num_ctx"]), num_predict=int(raw["num_predict"]))
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("[vllm_limits] invalid probe file %s: %s", p, exc)
        return None


def clamp_model_limits(
    *,
    requested_ctx: int,
    requested_predict: int,
    probe: VllmLimits | None,
) -> tuple[int, int]:
    """要求値をプローブ結果でクランプする。"""
    if probe is None:
        return requested_ctx, requested_predict
    ctx = min(requested_ctx, probe.num_ctx)
    predict = min(requested_predict, probe.num_predict)
    if ctx < requested_ctx or predict < requested_predict:
        logger.warning(
            "[vllm_limits] clamping num_ctx %s→%s, num_predict %s→%s (probe)",
            requested_ctx,
            ctx,
            requested_predict,
            predict,
        )
    return ctx, predict


def write_probe_limits(
    path: str | Path,
    limits: VllmLimits,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """プローブ結果を JSON に書き出す。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "num_ctx": limits.num_ctx,
        "num_predict": limits.num_predict,
    }
    if extra:
        payload.update(extra)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
