"""vLLM VRAM 上限プローブ。"""

from __future__ import annotations

import gc
import sys
from pathlib import Path

from joryu.config import load_config
from joryu.paths import DEFAULT_CONFIG, resolve_limits_probe_path, resolve_repo_root
from joryu.vllm_limits import (
    PROBE_CANDIDATES,
    VllmLimits,
    is_vram_limit_error,
    vllm_config_fingerprint,
    write_probe_limits,
)


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
    kv_cache_dtype: str = "auto",
    enable_prefix_caching: bool = False,
    max_num_seqs: int | None = None,
    swap_space_gib: int = 0,
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
    if kv_cache_dtype and kv_cache_dtype != "auto":
        llm_kwargs["kv_cache_dtype"] = kv_cache_dtype
    if enable_prefix_caching:
        llm_kwargs["enable_prefix_caching"] = True
    if max_num_seqs is not None and max_num_seqs > 0:
        llm_kwargs["max_num_seqs"] = max_num_seqs
    if swap_space_gib and swap_space_gib > 0:
        llm_kwargs["swap_space"] = swap_space_gib

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
    kv_cache_dtype: str = "auto",
    enable_prefix_caching: bool = False,
    max_num_seqs: int | None = None,
    swap_space_gib: int = 0,
) -> VllmLimits | None:
    """候補を降順で試行し、成功した最大 (num_ctx, num_predict) を返す。"""
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
                kv_cache_dtype=kv_cache_dtype,
                enable_prefix_caching=enable_prefix_caching,
                max_num_seqs=max_num_seqs,
                swap_space_gib=swap_space_gib,
            )
            print(f"[probe] OK num_ctx={num_ctx} num_predict={num_predict}", flush=True)
            return VllmLimits(num_ctx=num_ctx, num_predict=num_predict)
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] failed: {exc}", flush=True)
            if not is_vram_limit_error(exc):
                raise
            gc.collect()
    return None


def run_probe(*, config: str | Path, out: str | Path | None = None) -> int:
    """config からプローブを実行し limits JSON を書き出す。"""
    repo = resolve_repo_root() or Path.cwd()
    cfg_path = Path(config)
    if not cfg_path.is_absolute():
        cfg_path = repo / cfg_path
    cfg = load_config(cfg_path)

    if out:
        out_path = Path(out)
    else:
        out_path = resolve_limits_probe_path(cfg.model.limits_probe_file, repo_root=repo)

    limits = probe_limits(
        model_path=cfg.vllm.model_path,
        dtype=cfg.vllm.dtype,
        quantization=cfg.vllm.quantization,
        gpu_memory_utilization=cfg.vllm.gpu_memory_utilization,
        enforce_eager=cfg.vllm.enforce_eager,
        seed=cfg.model.seed,
        kv_cache_dtype=cfg.vllm.kv_cache_dtype,
        enable_prefix_caching=cfg.vllm.enable_prefix_caching,
        max_num_seqs=cfg.vllm.max_num_seqs,
        swap_space_gib=cfg.vllm.swap_space_gib,
    )
    if limits is None:
        print("[probe] all candidates failed", file=sys.stderr)
        return 1

    write_probe_limits(
        out_path,
        limits,
        extra={"config_fingerprint": vllm_config_fingerprint(cfg)},
    )
    print(f"[probe] wrote {out_path}")
    return 0


def run_vllm_probe(
    *,
    config: str | Path = DEFAULT_CONFIG,
    out: str | Path | None = None,
    image: str | None = None,
    force_docker: bool = False,
    force_native: bool = False,
) -> int:
    """ホストまたは Docker delegate 経由で VRAM プローブを実行する。"""
    from joryu.docker_delegate import DEFAULT_IMAGE, run_in_docker, should_use_docker

    config_str = str(config)
    extra: list[str] = []
    if out:
        extra.extend(["--out", str(out)])
    docker_image = image or DEFAULT_IMAGE

    if should_use_docker(force_docker=force_docker, force_native=force_native):
        return run_in_docker(
            image=docker_image,
            config=config_str,
            extra_args=extra,
            cli_module="joryu.cli.probe_vllm",
            native_flag="--no-docker",
        )
    return run_probe(config=config, out=out)
