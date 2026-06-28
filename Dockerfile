# joryu app コンテナ。joryu-vllm-base 上にアプリ層のみ追加 (vLLM 再コンパイル回避)。
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

FROM joryu-vllm-base:latest

LABEL org.opencontainers.image.source="https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline"

WORKDIR /app

COPY --from=builder /app/src /app/src
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY --from=builder /app/uv.lock /app/uv.lock
COPY --from=builder /app/config.yaml /app/config.yaml
COPY --from=builder /app/styles.yaml /app/styles.yaml
COPY --from=builder /app/tools.yaml /app/tools.yaml
COPY --from=builder /app/README.md /app/README.md

RUN uv sync --frozen --no-dev --extra api

ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH} \
    VLLM_USE_DEEP_GEMM=0 \
    VLLM_DEEP_GEMM_WARMUP=skip \
    VLLM_USE_FLASHINFER_SAMPLER=0

CMD ["vllm", "serve", "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4", "--host=0.0.0.0", "--port=8100", "--quantization=awq_marlin", "--dtype=bfloat16", "--max-model-len=4096", "--gpu-memory-utilization=0.85", "--kv-cache-dtype=fp8", "--enable-prefix-caching", "--max-num-seqs=1", "--enforce-eager", "--enable-auto-tool-choice", "--tool-call-parser=hermes", "--reasoning-parser=qwen3"]
