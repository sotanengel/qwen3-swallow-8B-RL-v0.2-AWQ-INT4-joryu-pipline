# qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline

Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4 (joryu) を使ったローカル日本語データ蒸留パイプライン。
生成された JSONL は他リポジトリの SFT 教師データとして利用する。

設計方針: [#1 Design Issue](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/1)

## 特徴

- **AWQ-INT4 ローカル推論** (vLLM + Marlin, RTX 3060 Ti 8GB 想定)
- **JSONL プロンプトバンク**: 1 行 = 1 プロンプト。`sampling` / `mode` / `system_prompt`
  を行単位で上書き可能。
- **推論 / 非推論 / 自動モード切替** (`--mode thinking|nothinking|auto`)
- **ツール呼び出し記録** (`tools.yaml` + JSONL 行 `tool_ids` / ad-hoc `tools`)
- **zstd 圧縮 + SHA256 + meta.json** で蒸留データを軽量に持ち運び
- **Next.js ダッシュボード**: 検索・分布可視化・**蒸留ジョブ投入** (`/jobs`)
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

# 2.5. GPU 上限プローブ（`joryu-up` 起動時に未作成・設定変更・joryu rebuild 時は自動実行）
# 手動のみ必要な場合:
# uv run joryu-probe-vllm

# 3. 推論モードで蒸留
uv run joryu-distill --count 50 --duration 1h

# 3b. 文体 × サンプリングの直積スイープ（同一プロンプトを複数条件で生成）
uv run joryu-distill --style polite,casual,expert --temperature 0.5,0.8,1.0 --top-p 0.8,0.9,0.95 --count 100

# 4. 非推論モードで蒸留
uv run joryu-distill --count 50 --mode nothinking

# 5. zstd 圧縮 + meta.json でエクスポート
uv run joryu-export --bundle-tar

# 6. ダッシュボード + API + vLLM 常駐デーモン起動
uv run joryu-up --detach

# 6b. ブラウザで http://localhost:3000/jobs から蒸留ジョブを投入
#     API: http://localhost:8000  (ローカル専用・認証なし)
#     vLLM デーモン: http://localhost:8100/health (モデルロード完了まで joryu-up が待機)
#     `--no-wait` で ready 待ちをスキップ可能
```

## フロント + バックエンドの起動 / 停止

```powershell
uv run joryu-up                  # dashboard + api + joryu (vLLM 常駐, git 差分に応じて build+up)
uv run joryu-up --full           # 上記と同義 (後方互換)
uv run joryu-up --detach         # バックグラウンド起動 + API/vLLM/dashboard ready 待ち
uv run joryu-up --no-wait        # ready 待ちをスキップ
uv run joryu-up --no-open        # ブラウザ自動起動を無効化
uv run joryu-up --force          # ディスク容量 preflight をスキップ
uv run joryu-up --frontend-only  # dashboard のみ (= joryu-serve と等価)
uv run joryu-up --backend-only   # joryu コンテナだけ
uv run joryu-up --no-build       # build をスキップして up のみ
uv run joryu-up --build          # up 対象を強制 rebuild
uv run joryu-up --refresh-stats  # 起動前に joryu-stats を回して描画を最新化
uv run joryu-down                # 停止 (volume は残す)
uv run joryu-down --volumes      # HF キャッシュ含めて完全に削除
```

`joryu-up` は git 作業ツリーの差分と、前回起動時の HEAD からのコミット差分（`git pull` 後など）から rebuild 対象を自動判定する。初回起動時は up 対象をすべて build する。**api / joryu を up する場合**、`data/vllm_limits.json` が無い・設定変更・joryu イメージ rebuild 時は起動前に `joryu-probe-vllm` を自動実行する。`--detach` 時は compose up 後に API (`/api/health`)、vLLM デーモン (`:8100/health`)、dashboard が ready になるまで待機する（`--no-wait` でスキップ）。ジョブは常駐 vLLM へ HTTP 接続し、GPU `docker run` を毎回起動しない。**デーモン稼働中に `joryu-distill --docker` を手動実行すると GPU OOM の恐れあり。**

## ジョブ API とダッシュボード

`joryu-api` (FastAPI, port 8000) が蒸留ジョブの投入・状態照会を担当する。ダッシュボードの `/jobs` 画面から `joryu-distill` 相当のパラメータで実行できる。

```powershell
# 既定起動 (dashboard + api + vLLM 常駐 joryu)
uv run joryu-up --detach

# ローカル開発 (GPU ジョブは常駐デーモンまたはホスト Docker 経由)
uv run joryu-api
cd dashboard && npm run dev
```

ジョブ状態は `data/jobs/` に JSON で永続化される（gitignore）。成功時は自動で `joryu-stats` が走り、概要ページの統計が更新される。

`/jobs` 画面では **mode**（`thinking` / `nothinking` / `auto`）、**文体**、**temperature / top_p スイープ**に加え、`tools.yaml` で定義された **ツール**（チェックボックス）と **tool 実行ループ**（`tool_loop` + `max_turns`）を指定できる。ツール ID はプロンプト行に `tool_ids` が無い行にのみ適用される（行に既存の `tool_ids` がある場合は行優先）。

api コンテナから GPU ジョブを実行する場合、Docker デーモンが参照できるホスト側リポジトリパスへ自動変換する（`/proc/self/mountinfo`）。解決できない場合のみ `JORYU_HOST_REPO_ROOT` を手動指定する。

**注意**: API は localhost 専用。認証は v1 では付けていない。

## `joryu-distill` CLI 引数

| 引数 | 例 | 説明 |
|---|---|---|
| `--config` | `config.yaml` | 設定ファイル |
| `--bank` | `data/prompts/foo.jsonl` | プロンプトバンク上書き |
| `--out` | `data/distilled/out.jsonl` | 出力 JSONL 上書き |
| `--count` | `50` | 新規レコード上限（0 = 未処理分すべて）。**バリアント含む総件数** |
| `--duration` | `1h30m` | 実行時間上限 |
| `--mode` | `thinking` / `nothinking` / `auto` | 推論 / 非推論 / モデル自己判定。カンマ区切りで直積可（例: `thinking,auto`） |
| `--style` | `polite,casual,expert` | 文体プリセット（[`styles.yaml`](styles.yaml) 参照） |
| `--temperature` | `0.5,0.7,1.0` | temperature スイープ（0.5〜1.0） |
| `--top-p` | `0.8,0.9,0.95` | top_p スイープ（0.8〜0.95） |
| `--tool-loop` | (フラグ) | tool_call をローカル実行して再生成ループを有効化 |
| `--max-turns` | `4` | `--tool-loop` 時の最大ターン数 |
| `--docker` / `--no-docker` | | Docker 委譲の強制 / 無効化 |

`--style` × `--temperature` × `--top-p` × `--mode`（複数指定時）は **直積（cartesian product）** で展開される。
例: 4,001 プロンプト × 3 文体 × 6 temperature × 4 top_p = **288,072 レコード** — `--count` で上限を必ず指定すること。

文体プリセットは [`styles.yaml`](styles.yaml) に定義。`config.yaml` の `distill.styles_file` でパスを変更可能。

ツール定義は [`tools.yaml`](tools.yaml) に集中管理。プロンプト行に `"tool_ids": ["search"]` を
指定するとモデルへ tools schema が渡され、出力 JSONL に `tools` / `tool_calls` が記録される。
ad-hoc 直書きは行の `"tools": [{...}]` で指定可能（同名衝突時は ad-hoc が優先）。

蒸留中は **stderr** に進捗・ETA・直近 5 件のプロンプト/回答が表示される。Docker 委譲時もホストが TTY なら `docker run -t` で `\r` 更新が有効。

## ディレクトリ概要

```
src/joryu/        Python パッケージ (config, prompt_bank, vllm_client, distill, export, stats, jobs, api)
styles.yaml       文体プリセット定義
tools.yaml        蒸留用ツール定義 (OpenAI / Qwen3 互換 JSON Schema)
src/joryu/cli/    CLI エントリポイント (joryu-distill, joryu-api 等)
dashboard/        Next.js ダッシュボード (App Router, TypeScript)
scripts/          開発スクリプト (setup-dev, check, migrate_csv_to_jsonl)
data/             ローカル生成データ (gitignore)
exports/          圧縮済み蒸留データ (gitignore)
```

## ドキュメント

- [docs/requirements.md](docs/requirements.md) — 機能要件・非機能要件
- [docs/architecture.md](docs/architecture.md) — モジュール構成図とレイヤー責務
- [docs/sft-consumer.md](docs/sft-consumer.md) — エクスポートデータを別リポジトリの SFT で使う手順

## エンドツーエンドスモーク (GPU 不要)

```bash
bash scripts/verify_pipeline.sh
```

Fake vLLM クライアントで `distill → export → stats` まで一通り走らせ、
`responses.jsonl.zst` / `meta.json` / `SHA256SUMS` / `stats.json` が
出ることを確認する。CI からも同じスクリプトが走る。

## ライセンス

Apache-2.0 (`LICENSE` 参照)。
