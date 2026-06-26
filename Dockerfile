# joryu app コンテナ。uv ビルド + NVIDIA CUDA ランタイム + vLLM。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY scripts ./scripts
COPY config.yaml ./config.yaml
COPY styles.yaml ./styles.yaml
COPY tools.yaml ./tools.yaml
COPY README.md ./README.md
RUN uv sync --frozen --no-dev --extra api

# cu130 + vLLM ランタイム。
# devel イメージ (nvcc 同梱) を使うのは FlashInfer が FP8 KV キャッシュ用の
# attention カーネルを JIT ビルドする際に /usr/local/cuda/bin/nvcc を必要とするため。
# runtime イメージだと kv_cache_dtype="fp8" の vLLM 起動が exit 127 で死ぬ。
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ninja-build \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

RUN uv pip install torch --python /app/.venv/bin/python \
       --index-url https://download.pytorch.org/whl/cu130 && \
    uv pip install vllm --python /app/.venv/bin/python

ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH} \
    VLLM_USE_DEEP_GEMM=0 \
    VLLM_DEEP_GEMM_WARMUP=skip \
    VLLM_USE_FLASHINFER_SAMPLER=0

CMD ["vllm", "serve", "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4", "--host=0.0.0.0", "--port=8100", "--quantization=awq_marlin", "--dtype=bfloat16", "--max-model-len=4096", "--gpu-memory-utilization=0.85", "--kv-cache-dtype=fp8", "--enable-prefix-caching", "--max-num-seqs=1", "--swap-space=4", "--enforce-eager", "--enable-auto-tool-choice", "--tool-call-parser=hermes", "--reasoning-parser=qwen3"]
