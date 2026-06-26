#!/usr/bin/env bash
# pytest + カバレッジ閾値チェック。pyproject.toml [tool.coverage.report] fail_under を適用する。
#
# 用法:
#   bash scripts/check_coverage.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[check-coverage] pytest with coverage threshold" >&2
fail_under="$(uv run python -c "import tomllib; from pathlib import Path; print(tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['tool']['coverage']['report']['fail_under'])")"
uv run pytest --cov=joryu --cov-report=term-missing --cov-fail-under="${fail_under}"
