#!/bin/bash
# llama-server 起動 (screening profile)。GGUF は gguf-cache volume に永続化。
set -euo pipefail

MODEL_FILE="${JORYU_JUDGE_MODEL:-Llama-3.1-Swallow-8B-Instruct-v0.5-Q4_K_M.gguf}"
MODEL_PATH="/models/${MODEL_FILE}"
HF_REPO="${JORYU_JUDGE_HF_REPO:-tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.5-GGUF}"
PORT="${JORYU_JUDGE_PORT:-8080}"

if [ ! -f "${MODEL_PATH}" ]; then
  echo "[joryu-judge] downloading GGUF: ${HF_REPO}/${MODEL_FILE}"
  huggingface-cli download "${HF_REPO}" "${MODEL_FILE}" --local-dir /models
fi

exec llama-server \
  --model "${MODEL_PATH}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --ctx-size 4096 \
  --n-gpu-layers 99
