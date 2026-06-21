#!/usr/bin/env bash
# ローカル CI ゲート。GitHub Actions の test + security ジョブと同等の検査を一括実行する。
# コミット・PR 前に必ず通すこと (AGENTS.md 参照)。
#
# 用法:
#   bash scripts/check.sh              # フル検査
#   bash scripts/check.sh --quick      # pytest 省略 (開発中のみ、PR 前は不可)
#   bash scripts/check.sh --skip-pre-commit
#   bash scripts/check.sh --skip-pytest
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

QUICK=0
SKIP_PRECOMMIT=0
SKIP_PYTEST=0

for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --skip-pre-commit) SKIP_PRECOMMIT=1 ;;
    --skip-pytest) SKIP_PYTEST=1 ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

log() { echo "[check] $*" >&2; }

log "ruff check"
uv run ruff check .

log "ruff format --check"
uv run ruff format --check .

if [ "$SKIP_PRECOMMIT" -eq 0 ]; then
  log "pre-commit run --all-files"
  uvx pre-commit run --all-files --show-diff-on-failure
fi

if [ "$QUICK" -eq 0 ] && [ "$SKIP_PYTEST" -eq 0 ]; then
  log "pytest"
  uv run pytest --cov=joryu --cov-report=term-missing
fi

log "OK: all checks passed"
