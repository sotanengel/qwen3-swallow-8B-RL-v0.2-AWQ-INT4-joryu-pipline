#!/usr/bin/env bash
# joryu-vllm-base:latest を進捗ログ付きでビルドする。
#
# image 構成 (PR #330 で分離):
#   - joryu-vllm-base:latest = torch + git vLLM コンパイル済みベース (本スクリプト)
#   - joryu / joryu-seed     = 常駐 vLLM サーバ、上記 base image を直接参照 (src/ なし)
#   - joryu-job:latest       = api からの compose run 用、base + src + uv sync
#                              手動 build: docker build -f Dockerfile.job -t joryu-job:latest .
#   - joryu-judge:latest     = llama.cpp + GGUF (Dockerfile.judge)
#
# 試行 1 (MAX_JOBS=1 + arch 全部 + progress=auto) で 2 時間以上の hang が
# 起きた反省から、以下を強制する:
#   - docker build --progress=plain     # setup.py の bdist_wheel 出力を可視化
#   - tee data/logs/build-vllm-base-<UTC>.log  # 中断時のためログ保存
#   - 前後タイムスタンプ + 所要秒数を stderr に出す
#
# Dockerfile.vllm-base 側で MAX_JOBS=4 / NVCC_THREADS=2 / TORCH_CUDA_ARCH_LIST=8.6
# を ENV として設定済み。本スクリプトは Docker build 起動時の体裁のみを担う。
#
# 用法:
#   bash scripts/build-vllm-base.sh                # フォアグラウンド (Cursor 等の
#                                                    # エージェント shell からは
#                                                    # 長時間で kill されやすい)
#   bash scripts/build-vllm-base.sh --detach         # バックグラウンド (別ターミナルで --watch)
#   bash scripts/build-vllm-base.sh --watch          # 進捗ログをリアルタイム表示 (推奨: 2 窓目)
#   bash scripts/build-vllm-base.sh --status         # スナップショット確認
#   JORYU_VLLM_BASE_TAG=joryu-vllm-base:latest \
#     bash scripts/build-vllm-base.sh --detach       # タグ上書き
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TAG="${JORYU_VLLM_BASE_TAG:-joryu-vllm-base:latest}"
DOCKERFILE="${JORYU_VLLM_BASE_DOCKERFILE:-Dockerfile.vllm-base}"
LOG_DIR="${ROOT}/data/logs"
PID_FILE="${LOG_DIR}/build-vllm-base.pid"
LATEST_LOG_POINTER="${LOG_DIR}/build-vllm-base-latest.path"

_resolve_latest_log() {
  if [ -f "$LATEST_LOG_POINTER" ]; then
    cat "$LATEST_LOG_POINTER"
    return 0
  fi
  # フォールバック: タイムスタンプ付きログの最新
  ls -1t "${LOG_DIR}"/build-vllm-base-2*.log 2>/dev/null | head -n 1
}

_run_status() {
  if [ -f "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "[build-vllm-base] running pid=${pid}"
    else
      echo "[build-vllm-base] stale pid file (pid=${pid} not running)"
    fi
  else
    echo "[build-vllm-base] no pid file (not running via --detach)"
  fi
  if docker image inspect "$TAG" >/dev/null 2>&1; then
    echo "[build-vllm-base] image exists: ${TAG}"
  else
    echo "[build-vllm-base] image missing: ${TAG}"
  fi
  log="$(_resolve_latest_log || true)"
  if [ -n "${log:-}" ] && [ -f "$log" ]; then
    echo "[build-vllm-base] log: ${log}"
    echo "--- tail ---"
    tail -n 20 "$log" 2>/dev/null || true
    echo "--- compile progress (last match) ---"
    grep -E '\[[0-9]+/337\]' "$log" 2>/dev/null | tail -n 3 || true
  fi
}

_run_watch() {
  log="$(_resolve_latest_log || true)"
  if [ -z "${log:-}" ] || [ ! -f "$log" ]; then
    echo "[build-vllm-base] log not found under ${LOG_DIR} (build not started yet?)" >&2
    exit 1
  fi
  echo "[build-vllm-base] watching ${log} (Ctrl-C to stop tail only; build continues)" >&2
  echo "[build-vllm-base] filter: docker steps, [N/337] compile, errors, start/end" >&2
  # BuildKit plain + uv -v は行数が多いので、見やすい行だけ通す。
  tail -n 30 -f "$log" | grep --line-buffered -E \
    '^\#|^\[build-vllm-base\]|Building CUDA|Building CXX| \[[0-9]+/337\]|DONE [0-9]|ERROR|failed to solve|unexpected EOF|Successfully tagged|naming to docker.io|exit_code:|elapsed_sec:'
}

if [ "${1:-}" = "--watch" ]; then
  _run_watch
  exit 0
fi

if [ "${1:-}" = "--status" ]; then
  _run_status
  exit 0
fi

if [ "${1:-}" = "--detach" ]; then
  if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "[build-vllm-base] already running pid=${old_pid} (see --status)" >&2
      exit 0
    fi
  fi
  mkdir -p "$LOG_DIR"
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  WRAP_LOG="${LOG_DIR}/build-vllm-base-wrapper-${TS}.log"
  nohup bash "$0" --foreground >>"$WRAP_LOG" 2>&1 &
  echo "$!" >"$PID_FILE"
  echo "[build-vllm-base] detached pid=$(cat "$PID_FILE") wrapper_log=${WRAP_LOG}" >&2
  echo "[build-vllm-base] watch:  bash scripts/build-vllm-base.sh --watch" >&2
  echo "[build-vllm-base] status: bash scripts/build-vllm-base.sh --status" >&2
  exit 0
fi

if [ "${1:-}" != "--foreground" ] && [ -n "${1:-}" ]; then
  echo "[build-vllm-base] unknown argument: $1 (use --detach, --foreground, --watch, --status)" >&2
  exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/build-vllm-base-${TS}.log"

mkdir -p "$LOG_DIR"

if [ ! -f "$DOCKERFILE" ]; then
  echo "[build-vllm-base] ERROR: $DOCKERFILE not found" >&2
  exit 1
fi

# Windows (Git Bash) では symlink が Developer Mode 無しで失敗するため path ファイルを使う。
echo "$LOG_FILE" >"$LATEST_LOG_POINTER"

START_EPOCH=$(date -u +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  echo "[build-vllm-base] start: ${START_ISO}"
  echo "[build-vllm-base] tag: ${TAG}"
  echo "[build-vllm-base] dockerfile: ${DOCKERFILE}"
  echo "[build-vllm-base] log: ${LOG_FILE}"
  echo "[build-vllm-base] pid: $$"
} >&2

# `--progress=plain` + `tee` でリアルタイム可視化 + 永続化。
status=0
docker build \
  --progress=plain \
  -f "$DOCKERFILE" \
  -t "$TAG" \
  "$ROOT" 2>&1 | tee "$LOG_FILE" || status=$?

END_EPOCH=$(date -u +%s)
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ELAPSED=$((END_EPOCH - START_EPOCH))

{
  echo "[build-vllm-base] end:   ${END_ISO}"
  echo "[build-vllm-base] elapsed_sec: ${ELAPSED}"
  echo "[build-vllm-base] log: ${LOG_FILE}"
  echo "[build-vllm-base] exit_code: ${status}"
} >&2

# detach 起動時の pid ファイルを掃除
if [ -f "$PID_FILE" ] && [ "$(cat "$PID_FILE")" = "$$" ]; then
  rm -f "$PID_FILE"
fi

exit "$status"
