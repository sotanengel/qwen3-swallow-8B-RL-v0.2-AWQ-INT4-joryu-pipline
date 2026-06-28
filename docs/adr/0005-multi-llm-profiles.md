# ADR 0005: マルチ LLM ModelProfile（8GB GPU 排他）

## ステータス

Accepted

## コンテキスト

RTX 3060 Ti (8GB VRAM) 上で次のワークフローをブラウザだけで完結させる必要がある:

1. 蒸留 (Qwen3-Swallow AWQ / vLLM)
2. プロンプト生成 (Qwen2.5-7B-Instruct-AWQ / vLLM)
3. プロンプト評価 (Llama-3.1-Swallow GGUF / llama-server)
4. 再蒸留 (Qwen3)

8B クラス LLM は **同時常駐不可**。現状は Qwen3 のみ compose 常駐で、seed-gen / screening judge は手動起動が前提だった。

## 決定

### ModelProfile を一級概念として導入

| Profile | Compose サービス | モデル |
|---------|-------------------|--------|
| `distill` | `joryu` | Qwen3-Swallow AWQ |
| `seed_gen` | `joryu-seed` | Qwen2.5-7B-Instruct-AWQ |
| `screening` | `joryu-judge` | Llama-3.1-Swallow GGUF Q4_K_M |

### FSM + 永続状態

- `ModelOrchestrator` が profile 切替を担当
- `data/active_profile.json` が永続的な真実（ファイルロック付き）
- 状態: `stopped` / `starting` / `active` / `switching` / `error`

### docker compose `profiles:`

- GPU サービスは compose profile で所属を宣言
- orchestrator は `docker compose --profile <p> up|stop` のみ呼ぶ
- `dashboard` / `api` / `mcp` は `always` profile で常時起動

### 単一情報源

- `config.yaml` の `models.profiles[]` に service / port / health / model を集約
- ジョブ種別から `required_profile()` を導出（JobKind は変更しない）

### SSE 状態配信

- `GET /api/system/models/stream` で profile 切替進捗を push

## 検討した代替案

1. **単一 vLLM で動的モデル切替** — vLLM が未対応のため却下
2. **LoRA + 共通ベース** — モデル種が異なり不可
3. **全モデル同時常駐** — 8GB で KV キャッシュ不足
4. **手動 llama-server 継続** — ブラウザ完結要件不達

## 影響

- ジョブ開始前に profile 切替が発生（warm ~30s、cold ~3min）
- `joryu-up` 既定は distill profile のみ up
- ジョブ完了後 `models.auto_restore: distill`（既定）で chat 可能状態へ復帰
- chat は distill profile active 時のみ許可（409）

## 関連

- Epic: ブラウザ完結マルチ LLM ワークフロー
- ADR 0003 (vllm-serve 本流)
