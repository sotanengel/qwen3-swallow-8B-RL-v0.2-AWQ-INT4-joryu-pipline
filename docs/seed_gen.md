# プロンプトシード生成 (joryu-seed-gen)

Epic #313: 既存 `training_prompts.jsonl`（`prompt` + `category`）との後方互換を保ちながら、
15 分野のシードプロンプトを LLM で追記生成する。

## クイックスタート

```bash
# 計画のみ
uv run joryu-seed-gen --dry-run --target-total 230000

# CI / ローカル smoke (Fake LLM)
uv run joryu-seed-gen --fake-llm --domain general_qa --target-total 20

# 本番 (vLLM ready 後)
uv run joryu-up --detach
uv run joryu-seed-gen --domain math --target-total 28000
```

## プロンプト LLM スクリーニング

生成後、プロンプトバンクを **LLM 単体**でスクリーニング:

```bash
JORYU_CURATE_FAKE_JUDGE=1 uv run joryu-curate \
  --screening --prompt-bank \
  --src data/prompts/training_prompts.jsonl \
  --dst data/curated/prompt_screening
```

## ダッシュボード

パイプラインハブ (`/?stage=prompts` および `/?stage=check`) から seed-gen ジョブ起動・分野進捗・手動追記・スクリーニング起動が可能。

**ブラウザ完結時**: `joryu-up` 後、seed-gen ジョブ投入で `ModelOrchestrator` が compose profile `seed_gen` の `joryu-seed` (Qwen2.5 / vLLM) を lazy 起動する。完了後は `config.yaml` の `models.auto_restore` (既定 `distill`) で Qwen3 蒸留用 profile に戻る。

## チェックポイント

- `data/seed_gen/state.json` — 分野別カウント・棄却率・**`prompt_check.checked_keys`**（チェック済みプロンプト）
- `--resume` で中断再開

## 増分プロンプトチェック

チェック済み状態は `state.json` の `prompt_check.checked_keys` に永続化される。

- **手動登録**: ダッシュボード `/?stage=check` または API `POST /api/seed-gen/check/mark`
- **増分実行**: seed_gen check / prompt-bank screening は未チェック行のみ処理
- **蒸留可否**: 未チェック 0 件 (`GET /api/seed-gen/check/status` の `check_completed`)

CLI 例:

```bash
# 未チェック全件をチェック済み登録 (実際に審査済みのプロンプトのみ)
uv run joryu-seed-gen --mark-checked --all-unchecked

# 特定キーを登録
uv run joryu-seed-gen --mark-checked --mark-keys id:uuid-1,hash:abc...
```

## VRAM / モデル

- 生成 LLM 既定: `Qwen/Qwen2.5-7B-Instruct-AWQ`（Swallow 系禁止）
- 埋め込み: `cl-nagoya/ruri-large`（optional、`--fake-llm` 時は FakeEmbedding）
