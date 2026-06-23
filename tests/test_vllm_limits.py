"""vllm_limits.py: プローブ結果の読み込みとクランプ。"""

from __future__ import annotations

import json

from joryu.vllm_limits import (
    VllmLimits,
    clamp_model_limits,
    is_vram_limit_error,
    load_probe_limits,
    write_probe_limits,
)

KV_CACHE_VALUE_ERROR = (
    "To serve at least one request with the model's max seq len (2048), "
    "0.28 GiB KV cache is needed, which is larger than the available KV cache "
    "memory (0.17 GiB). Try increasing `gpu_memory_utilization` or decreasing "
    "`max_model_len` when initializing the engine."
)


def test_is_vram_limit_error_kv_cache_value_error() -> None:
    assert is_vram_limit_error(ValueError(KV_CACHE_VALUE_ERROR))


def test_is_vram_limit_error_cuda_oom() -> None:
    assert is_vram_limit_error(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))


def test_is_vram_limit_error_unrelated() -> None:
    assert not is_vram_limit_error(ValueError("invalid config"))
    assert not is_vram_limit_error(RuntimeError("connection refused"))


def test_load_probe_limits_missing(tmp_path) -> None:
    assert load_probe_limits(tmp_path / "nope.json") is None


def test_load_probe_limits_valid(tmp_path) -> None:
    path = tmp_path / "limits.json"
    path.write_text(json.dumps({"num_ctx": 1024, "num_predict": 640}), encoding="utf-8")
    limits = load_probe_limits(path)
    assert limits == VllmLimits(num_ctx=1024, num_predict=640)


def test_clamp_model_limits_without_probe() -> None:
    ctx, predict = clamp_model_limits(
        requested_ctx=2048,
        requested_predict=1024,
        probe=None,
    )
    assert ctx == 2048
    assert predict == 1024


def test_clamp_model_limits_with_probe(tmp_path) -> None:
    path = tmp_path / "limits.json"
    write_probe_limits(path, VllmLimits(num_ctx=768, num_predict=512))
    probe = load_probe_limits(path)
    ctx, predict = clamp_model_limits(
        requested_ctx=2048,
        requested_predict=1024,
        probe=probe,
    )
    assert ctx == 768
    assert predict == 512
