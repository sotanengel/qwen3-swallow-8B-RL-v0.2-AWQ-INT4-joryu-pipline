#!/usr/bin/env python3
"""vLLM の VRAM 上限をプローブし、data/vllm_limits.json に書き出す。

OOM 時は候補を降順で試行し、成功した最大 (num_ctx, num_predict) を採用する。
"""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

from joryu.config import load_config
from joryu.paths import DEFAULT_CONFIG, resolve_repo_root
from joryu.vllm_limits import PROBE_CANDIDATES, VllmLimits, write_probe_limits


def _is_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "cuda" in text or "oom" in text


def _probe_once(
    *,
    model_path: str,
    dtype: str,
    quantization: str | None,
    gpu_memory_utilization: float,
    enforce_eager: bool,
    num_ctx: int,
    num_predict: int,
    seed: int,
) -> None:
    from vllm import LLM, SamplingParams

    llm_kwargs: dict = {
        "model": model_path,
        "max_model_len": num_ctx,
        "dtype": dtype,
        "enforce_eager": enforce_eager,
        "gpu_memory_utilization": gpu_memory_utilization,
        "seed": seed,
    }
    if quantization:
        llm_kwargs["quantization"] = quantization

    llm = LLM(**llm_kwargs)
    try:
        params = SamplingParams(max_tokens=min(num_predict, 32), temperature=0.0)
        messages = [{"role": "user", "content": "こんにちは"}]
        llm.chat(messages, params, use_tqdm=False)
    finally:
        del llm
        gc.collect()


def probe_limits(
    *,
    model_path: str,
    dtype: str,
    quantization: str | None,
    gpu_memory_utilization: float,
    enforce_eager: bool,
    seed: int,
    candidates: tuple[tuple[int, int], ...] = PROBE_CANDIDATES,
) -> VllmLimits | None:
    for num_ctx, num_predict in candidates:
        print(f"[probe] trying num_ctx={num_ctx} num_predict={num_predict}", flush=True)
        try:
            _probe_once(
                model_path=model_path,
                dtype=dtype,
                quantization=quantization,
                gpu_memory_utilization=gpu_memory_utilization,
                enforce_eager=enforce_eager,
                num_ctx=num_ctx,
                num_predict=num_predict,
                seed=seed,
            )
            print(f"[probe] OK num_ctx={num_ctx} num_predict={num_predict}", flush=True)
            return VllmLimits(num_ctx=num_ctx, num_predict=num_predict)
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] failed: {exc}", flush=True)
            if not _is_oom(exc):
                raise
            gc.collect()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe vLLM VRAM limits for joryu.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="config YAML path")
    parser.add_argument(
        "--out",
        default="",
        help="output JSON path (default: config.model.limits_probe_file)",
    )
    args = parser.parse_args(argv)

    repo = resolve_repo_root()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = repo / cfg_path
    cfg = load_config(cfg_path)

    out_path = Path(args.out) if args.out else Path(cfg.model.limits_probe_file)
    if not out_path.is_absolute():
        out_path = repo / out_path

    limits = probe_limits(
        model_path=cfg.vllm.model_path,
        dtype=cfg.vllm.dtype,
        quantization=cfg.vllm.quantization,
        gpu_memory_utilization=cfg.vllm.gpu_memory_utilization,
        enforce_eager=cfg.vllm.enforce_eager,
        seed=cfg.model.seed,
    )
    if limits is None:
        print("[probe] all candidates failed", file=sys.stderr)
        return 1

    write_probe_limits(out_path, limits)
    print(f"[probe] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
