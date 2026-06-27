#!/usr/bin/env bash
# 蒸留データ品質スモーク (#220 / #237)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify-distill-quality] running regression tests" >&2
uv run pytest tests/test_distill_quality_regression.py tests/test_completion_normalize.py \
  tests/curate/test_signals_quality.py tests/test_prompt_dedup.py -q

echo "[verify-distill-quality] OK" >&2
