"""vLLM VRAM プローブ結果の読み込みと設定クランプ。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from joryu.config import Config

logger = logging.getLogger(__name__)

PROBE_CANDIDATES: tuple[tuple[int, int], ...] = (
    # KV cache FP8 + max_num_seqs=1 + prefix caching が効くと
    # 2048 上限を超える領域もプローブできるようになる。
    (4096, 2048),
    (3072, 1536),
    (2048, 1024),
    (1536, 768),
    (1280, 640),
    (1024, 640),
    (768, 512),
    (512, 384),
)


_VRAM_LIMIT_MARKERS: tuple[str, ...] = (
    "out of memory",
    "cuda oom",
    " oom",
    "kv cache",
    "max_model_len",
    "max seq len",
    "gpu_memory_utilization",
    "available kv cache memory",
    "not enough memory",
    # vLLM v1: 子プロセスの KV cache 不足が親で RuntimeError に包まれる
    "engine core initialization failed",
)


def is_vram_limit_error(exc: BaseException) -> bool:
    """OOM や KV キャッシュ不足など VRAM 制限による vLLM 起動失敗か判定する。"""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if any(m in text for m in _VRAM_LIMIT_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass(frozen=True)
class VllmLimits:
    num_ctx: int
    num_predict: int


def vllm_config_fingerprint(cfg: Config) -> str:
    """model / vllm 設定の SHA256。プローブ結果の鮮度判定に使う。"""
    payload = json.dumps(
        {"model": asdict(cfg.model), "vllm": asdict(cfg.vllm)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return "sha256-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def limits_probe_stale(path: Path, fingerprint: str) -> bool:
    """limits ファイルが無いか、記録 fingerprint と不一致なら True。"""
    if not path.is_file():
        return True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(raw, dict):
        return True
    return raw.get("config_fingerprint") != fingerprint


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
