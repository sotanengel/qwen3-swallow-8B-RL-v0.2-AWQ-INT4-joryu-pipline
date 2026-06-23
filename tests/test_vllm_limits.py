"""vllm_limits.py: プローブ結果の読み込みとクランプ。"""

from __future__ import annotations

import json

from joryu.vllm_limits import (
    VllmLimits,
    clamp_model_limits,
    is_vram_limit_error,
    limits_probe_stale,
    load_probe_limits,
    vllm_config_fingerprint,
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


def test_is_vram_limit_error_engine_core_wrapper() -> None:
    """vLLM v1 が KV cache 不足を EngineCore RuntimeError に包むケース。"""
    exc = RuntimeError(
        "Engine core initialization failed. See root cause above. Failed core proc(s): {}"
    )
    assert is_vram_limit_error(exc)


def test_is_vram_limit_error_chained_kv_cache() -> None:
    inner = ValueError(KV_CACHE_VALUE_ERROR)
    outer = RuntimeError("Engine core initialization failed")
    outer.__cause__ = inner
    assert is_vram_limit_error(outer)


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


def test_vllm_config_fingerprint_changes_with_num_ctx() -> None:
    from joryu.config import Config

    cfg_a = Config()
    cfg_b = Config()
    cfg_b.model.num_ctx = 1024
    fp_a = vllm_config_fingerprint(cfg_a)
    fp_b = vllm_config_fingerprint(cfg_b)
    assert fp_a != fp_b
    assert fp_a.startswith("sha256-")


def test_vllm_config_fingerprint_changes_with_memory_savers() -> None:
    """KV cache dtype や prefix caching を変えるとプローブ結果は再取得すべき。"""
    from joryu.config import Config

    cfg_a = Config()
    cfg_b = Config()
    cfg_b.vllm.kv_cache_dtype = "auto"
    assert vllm_config_fingerprint(cfg_a) != vllm_config_fingerprint(cfg_b)

    cfg_c = Config()
    cfg_c.vllm.enable_prefix_caching = False
    assert vllm_config_fingerprint(cfg_a) != vllm_config_fingerprint(cfg_c)

    cfg_d = Config()
    cfg_d.vllm.max_num_seqs = 8
    assert vllm_config_fingerprint(cfg_a) != vllm_config_fingerprint(cfg_d)


def test_probe_candidates_descend_from_4k() -> None:
    """プローブ候補はメモリ節約後の上限を狙えるよう 4096 から降順で並ぶ。"""
    from joryu.vllm_limits import PROBE_CANDIDATES

    assert PROBE_CANDIDATES[0] == (4096, 2048)
    # 既存の (2048, 1024) は保険として必ず含まれる
    assert (2048, 1024) in PROBE_CANDIDATES
    # num_ctx は厳密に降順
    ctxs = [c for c, _ in PROBE_CANDIDATES]
    assert ctxs == sorted(ctxs, reverse=True)


def test_limits_probe_stale_missing_file(tmp_path) -> None:
    assert limits_probe_stale(tmp_path / "missing.json", "sha256-abc") is True


def test_limits_probe_stale_mismatch(tmp_path) -> None:
    path = tmp_path / "limits.json"
    write_probe_limits(
        path,
        VllmLimits(num_ctx=1024, num_predict=640),
        extra={"config_fingerprint": "sha256-old"},
    )
    assert limits_probe_stale(path, "sha256-new") is True
    assert limits_probe_stale(path, "sha256-old") is False
