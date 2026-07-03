# 補助モジュール存続判定 (#245)

Issue #245 の Go/No-Go 記録。親 Epic: #241。

| モジュール | 判定 | 根拠 |
|---|---|---|
| `distill/live.py` | **保持** | `distill/pipeline.py` → stats JSON → `DistillLiveAlertBanner.tsx` |
| `persistence/record_replay.py` | **保持** | `scripts/verify_pipeline.sh` step 1c / `verify_record_replay.py` |
| `infra/browser.py` | **保持** | `joryu-up --no-open` 経路 |
| `mcp/runtime.py` | **保持** | MCP 本流 (`api/app.py`, `tooling/executor.py`, preflight) |
| `vllm/probe.py` | **保持** | `joryu-up` 起動前プローブ |
| `vllm/limits.py` | **保持** | preflight / jobs runner |

削除 PR は不要。将来 `record_replay.py` を verify スクリプト内にインライン化する案は別 Issue で検討。

注記: 上記 6 モジュールはいずれもパッケージ再編（#405）でフラット配置から現在のパスへ移動済み
（判定内容・根拠は変わらず、ファイルパスのみ更新）。

関連 ADR: [0004-cli-compat-flags.md](adr/0004-cli-compat-flags.md)
