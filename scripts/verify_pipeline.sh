#!/usr/bin/env bash
# end-to-end スモーク (GPU 不要)。
#
# Fake vLLM クライアント経由で distill → export → stats まで走らせ、
# dashboard が読める形の JSON が出ることを確認する。
# CI からも呼べる。Linux/macOS/Git Bash on Windows いずれでも動く。
#
# 用法:
#   bash scripts/verify_pipeline.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# プロジェクト直下に .verify-tmp/ を作る (.gitignore で除外されている data/ 配下を使う)。
work="data/.verify-tmp"
rm -rf "$work"
mkdir -p "$work"

bank="$work/bank.jsonl"
out="$work/responses.jsonl"
exp_dir="$work/exports"
stats="$work/stats.json"
cfg="$work/c.yaml"

cat > "$bank" <<'EOF'
{"prompt":"桜の特徴を3行で説明してください","category":"国語"}
{"prompt":"1+1はいくつですか？","category":"数学","mode":"nothinking"}
{"prompt":"日本の首都はどこ？","category":"地理","sampling":{"temperature":0.2,"max_tokens":256}}
EOF

cat > "$cfg" <<EOF
distill:
  prompt_bank: "$bank"
  out_dir: "$work"
  out_file: "responses.jsonl"
export:
  out_dir: "$exp_dir"
  level: 3
EOF

echo "[verify] step 1: joryu-distill (FakeVllmClient via tests harness)" >&2
JORYU_VERIFY_CFG="$cfg" uv run python - <<'PY'
import os, sys

sys.path.insert(0, "tests")
from joryu.cli import distill as cli
from conftest import FakeVllmClient

fake = FakeVllmClient(answer="テスト回答", thinking="テスト思考")
rc = cli.main(["--no-docker", "--config", os.environ["JORYU_VERIFY_CFG"]], _client=fake)
sys.exit(rc)
PY

if [ ! -s "$out" ]; then
  echo "[verify] FAIL: responses.jsonl not written" >&2
  exit 1
fi
lines=$(grep -c . < "$out" || true)
echo "[verify]  -> wrote $lines records" >&2

echo "[verify] step 2: joryu-export" >&2
uv run joryu-export --config "$cfg" --input "$out" --out-dir "$exp_dir" --level 3

sub="$(find "$exp_dir" -mindepth 1 -maxdepth 1 -type d | head -n1)"
test -f "$sub/responses.jsonl.zst" || { echo "[verify] FAIL: zst missing"; exit 1; }
test -f "$sub/meta.json" || { echo "[verify] FAIL: meta.json missing"; exit 1; }
test -f "$sub/SHA256SUMS" || { echo "[verify] FAIL: SHA256SUMS missing"; exit 1; }
echo "[verify]  -> $sub OK" >&2

echo "[verify] step 3: joryu-stats" >&2
uv run joryu-stats --config "$cfg" --input "$out" --output "$stats"
test -s "$stats" || { echo "[verify] FAIL: stats.json empty"; exit 1; }
total=$(uv run python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['total'])" "$stats")
echo "[verify]  -> stats.total=$total" >&2

echo "[verify] OK: end-to-end smoke passed" >&2
