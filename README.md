# qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline

Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4 (joryu) を使ったローカル日本語データ蒸留パイプライン。
生成された JSONL は他リポジトリの SFT 教師データとして利用する。

設計方針: [#1 Design Issue](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/1)

## 特徴

- **AWQ-INT4 ローカル推論** (vLLM + Marlin, RTX 3060 Ti 8GB 想定)
- **JSONL プロンプトバンク**: 1 行 = 1 プロンプト。`sampling` / `mode` / `system_prompt`
  を行単位で上書き可能。
- **推論 / 非推論モード切替** (`--mode thinking|nothinking`)
- **zstd 圧縮 + SHA256 + meta.json** で蒸留データを軽量に持ち運び
- **Next.js ダッシュボード**: 検索・分布可視化
- すべて **Docker** で動作 (Windows → コンテナへ自動委譲)
- TDD: ruff / pre-commit / pytest / GitHub Actions

## セットアップ

```bash
bash scripts/setup-dev.sh   # uv sync + pre-commit/pre-push 登録
bash scripts/check.sh       # コミット前に必ず通す
```

## クイックスタート (実装完了後)

```powershell
# 1. プロンプトCSVを取り込んで JSONL バンクへ
uv run python scripts/migrate_csv_to_jsonl.py --src <path-to-csv> --dst data/prompts/training_prompts.jsonl

# 2. Docker イメージビルド
docker compose build joryu

# 3. 推論モードで蒸留
uv run joryu-distill --count 50 --duration 1h

# 4. 非推論モードで蒸留
uv run joryu-distill --count 50 --mode nothinking

# 5. zstd 圧縮 + meta.json でエクスポート
uv run joryu-export --bundle-tar

# 6. ダッシュボード起動 (http://localhost:3000)
uv run joryu-serve
```

## ディレクトリ概要

```
src/joryu/        Python パッケージ (config, prompt_bank, vllm_client, distill, export, stats)
src/joryu/cli/    CLI エントリポイント (joryu-distill 等)
dashboard/        Next.js ダッシュボード (App Router, TypeScript)
scripts/          開発スクリプト (setup-dev, check, migrate_csv_to_jsonl)
data/             ローカル生成データ (gitignore)
exports/          圧縮済み蒸留データ (gitignore)
```

## ライセンス

Apache-2.0 (`LICENSE` 参照)。
