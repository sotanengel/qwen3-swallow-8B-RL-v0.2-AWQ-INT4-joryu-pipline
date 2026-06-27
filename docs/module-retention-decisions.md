# 補助モジュール存続判定 (#245)

Issue #245 の Go/No-Go 記録。親 Epic: #241。

| モジュール | 判定 | 根拠 |
|---|---|---|
| `distill_live.py` | **保持** | `distill.py` → stats JSON → `DistillLiveAlertBanner.tsx` |
| `record_replay.py` | **保持** | `scripts/verify_pipeline.sh` step 1c / `verify_record_replay.py` |
| `browser.py` | **保持** | `joryu-up --no-open` 経路 |
| `mcp_runtime.py` | **保持** | MCP 本流 (`api/app.py`, `tool_executor.py`, preflight) |
| `vllm_probe.py` | **保持** | `joryu-up` 起動前プローブ |
| `vllm_limits.py` | **保持** | preflight / jobs runner |

削除 PR は不要。将来 `record_replay.py` を verify スクリプト内にインライン化する案は別 Issue で検討。

関連 ADR: [0004-cli-compat-flags.md](adr/0004-cli-compat-flags.md)
