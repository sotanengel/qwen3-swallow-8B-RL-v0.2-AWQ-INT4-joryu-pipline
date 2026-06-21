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

# 3b. 文体 × サンプリングの直積スイープ（同一プロンプトを複数条件で生成）
uv run joryu-distill --style polite,casual,expert --temperature 0.5,0.8,1.0 --top-p 0.8,0.9,0.95 --count 100

# 4. 非推論モードで蒸留
uv run joryu-distill --count 50 --mode nothinking

# 5. zstd 圧縮 + meta.json でエクスポート
uv run joryu-export --bundle-tar

# 6. ダッシュボード起動 (http://localhost:3000)
uv run joryu-serve
```

## `joryu-distill` CLI 引数

| 引数 | 例 | 説明 |
|---|---|---|
| `--config` | `config.yaml` | 設定ファイル |
| `--bank` | `data/prompts/foo.jsonl` | プロンプトバンク上書き |
| `--out` | `data/distilled/out.jsonl` | 出力 JSONL 上書き |
| `--count` | `50` | 新規レコード上限（0 = 未処理分すべて）。**バリアント含む総件数** |
| `--duration` | `1h30m` | 実行時間上限 |
| `--mode` | `thinking` / `nothinking` | 推論 / 非推論 |
| `--style` | `polite,casual,expert` | 文体プリセット（[`styles.yaml`](styles.yaml) 参照） |
| `--temperature` | `0.5,0.7,1.0` | temperature スイープ（0.5〜1.0） |
| `--top-p` | `0.8,0.9,0.95` | top_p スイープ（0.8〜0.95） |
| `--docker` / `--no-docker` | | Docker 委譲の強制 / 無効化 |

`--style` × `--temperature` × `--top-p` は **直積（cartesian product）** で展開される。
例: 4,001 プロンプト × 3 文体 × 6 temperature × 4 top_p = **288,072 レコード** — `--count` で上限を必ず指定すること。

文体プリセットは [`styles.yaml`](styles.yaml) に定義。`config.yaml` の `distill.styles_file` でパスを変更可能。

蒸留中は **stderr** に進捗・ETA・直近 5 件のプロンプト/回答が表示される。Docker 委譲時もホストが TTY なら `docker run -t` で `\r` 更新が有効。

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
