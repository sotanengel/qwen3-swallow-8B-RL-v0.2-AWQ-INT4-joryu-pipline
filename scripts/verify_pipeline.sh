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
{"prompt":"1+1はいくつですか？","category":"数学"}
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
cp "$ROOT/tools.yaml" "$work/tools.yaml"

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

echo "[verify] step 1b: tools smoke distill" >&2
tools_bank="$work/tools_smoke.jsonl"
tools_out="$work/tools_responses.jsonl"
cat > "$tools_bank" <<'EOF'
{"prompt":"東京の今日の天気を調べて要約してください","tool_ids":["search"]}
EOF
export JORYU_VERIFY_CFG="$cfg"
export JORYU_VERIFY_TOOLS_BANK="$tools_bank"
export JORYU_VERIFY_TOOLS_OUT="$tools_out"
uv run python - <<'PY'
import os, sys

sys.path.insert(0, "tests")
from joryu.cli import distill as cli
from conftest import FakeVllmClient

tool_call = '<tool_call>{"name":"search","arguments":{"query":"東京 天気"}}</tool_call>'
fake = FakeVllmClient(answer=tool_call + "\n要約。", thinking=None)
rc = cli.main(
    [
        "--no-docker",
        "--config",
        os.environ["JORYU_VERIFY_CFG"],
        "--bank",
        os.environ["JORYU_VERIFY_TOOLS_BANK"],
        "--out",
        os.environ["JORYU_VERIFY_TOOLS_OUT"],
    ],
    _client=fake,
)
sys.exit(rc)
PY
test -s "$tools_out" || { echo "[verify] FAIL: tools smoke jsonl missing"; exit 1; }
echo "[verify] step 1c: verify_record_replay" >&2
uv run python scripts/verify_record_replay.py "$tools_out"

echo "[verify] step 1d: tool-loop smoke distill" >&2
loop_bank="$work/tools_loop.jsonl"
loop_out="$work/tools_loop_responses.jsonl"
cat > "$loop_bank" <<'EOF'
{"prompt":"23 * 47 + 119 を計算してください","tool_ids":["calc"]}
EOF
export JORYU_VERIFY_LOOP_BANK="$loop_bank"
export JORYU_VERIFY_LOOP_OUT="$loop_out"
uv run python - <<'PY'
import os, sys

sys.path.insert(0, "tests")
from joryu.cli import distill as cli
from conftest import FakeVllmClient

turn1 = '<tool_call>{"name":"calc","arguments":{"expression":"23*47+119"}}</tool_call>'
fake = FakeVllmClient(answers=[turn1, "計算結果は 1200 です。"], thinking=None)
rc = cli.main(
    [
        "--no-docker",
        "--config",
        os.environ["JORYU_VERIFY_CFG"],
        "--bank",
        os.environ["JORYU_VERIFY_LOOP_BANK"],
        "--out",
        os.environ["JORYU_VERIFY_LOOP_OUT"],
        "--tool-loop",
    ],
    _client=fake,
)
sys.exit(rc)
PY
test -s "$loop_out" || { echo "[verify] FAIL: tool-loop smoke jsonl missing"; exit 1; }

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

echo "[verify] step 4: joryu-curate (FakeJudgeClient via env flag)" >&2
curate_dst="$work/curated"
JORYU_CURATE_FAKE_JUDGE=1 uv run joryu-curate \
  --config "$cfg" --src "$out" --dst "$curate_dst" --threshold 0.0
test -f "$curate_dst/responses.high_quality.jsonl" || {
  echo "[verify] FAIL: high_quality.jsonl missing"; exit 1
}
test -f "$curate_dst/scores.jsonl" || { echo "[verify] FAIL: scores.jsonl missing"; exit 1; }
test -f "$curate_dst/curation_meta.json" || {
  echo "[verify] FAIL: curation_meta.json missing"; exit 1
}
kept=$(uv run python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['summary']['kept'])" "$curate_dst/curation_meta.json")
echo "[verify]  -> curate kept=$kept" >&2

echo "[verify] step 4b: joryu-seed-gen CLI smoke (--mode check, empty bank)" >&2
seed_bank="$work/prompt_bank.jsonl"
# fake-llm を廃止したので、実 LLM/実埋め込み無しでも 0 を返す check モード
# (空バンク → early return) で CLI が起動できることだけ確認する。
uv run joryu-seed-gen \
  --mode check \
  --bank "$seed_bank" \
  --domain general_qa \
  --target-total 10 \
  --batch-size 4
echo "[verify]  -> seed_gen check CLI OK" >&2

echo "[verify] step 5: joryu-stats --curation" >&2
uv run joryu-stats --config "$cfg" --input "$out" --output "$stats" \
  --curation "$curate_dst" --curation-output "$work/curation.json"
test -s "$work/curation.json" || { echo "[verify] FAIL: curation.json empty"; exit 1; }
echo "[verify]  -> curation.json written" >&2

echo "[verify] step 6: chat SSE progress + streaming smoke" >&2
uv run python - <<'PY'
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "tests")
from fastapi.testclient import TestClient

from conftest import FakeStreamClient, FakeVllmClient
from joryu.api.app import create_app

root = Path(".")
work = root / "data" / ".verify-tmp"
work.mkdir(parents=True, exist_ok=True)
(work / "config.yaml").write_text(
    (root / "config.yaml").read_text(encoding="utf-8"),
    encoding="utf-8",
)
for name in ("styles.yaml", "tools.yaml"):
    (work / name).write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8")
(work / "data" / "distilled").mkdir(parents=True, exist_ok=True)

os.environ["JORYU_ORCHESTRATOR_BACKEND"] = "fake"
app = create_app(repo_root=work)
app.state.chat_client = FakeVllmClient(answer="fallback", thinking=None)
app.state.stream_chat_client = FakeStreamClient(answer="streamed")
client = TestClient(app)

created = client.post("/api/chat/sessions").json()
session_id = created["session_id"]
with client.stream(
    "POST",
    f"/api/chat/sessions/{session_id}/messages",
    json={"prompt": "hello"},
) as resp:
    assert resp.status_code == 200
    body = resp.read().decode("utf-8")

events: list[tuple[str, dict]] = []
for block in body.strip().split("\n\n"):
    if not block.strip():
        continue
    event_type = ""
    data_line = ""
    for line in block.split("\n"):
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            data_line = line[6:]
    if event_type and data_line:
        events.append((event_type, json.loads(data_line)))

types = [t for t, _ in events]
assert "column_start" in types, types
assert "turn_start" in types, types
assert "token" in types, types
assert types.index("column_start") < types.index("token")
assert types.index("token") < types.index("column_done")
print("[verify]  -> chat SSE order OK", file=sys.stderr)
PY

echo "[verify] OK: end-to-end smoke passed" >&2

bash scripts/verify_distill_quality.sh
