# Agent 向け開発ルール

## ローカル vs GitHub Actions

### コミット時（pre-commit フック・高速・必須）

`setup-dev.sh` が登録する pre-commit が lint / format / セキュリティ検査を実行する。

- ruff / zizmor / pinact / JSONL lint 等
- `--no-verify` でフックを迂回することは禁止

### PR 時（GitHub Actions・重い検査はここに一任）

`.github/workflows/ci.yml` の GitHub Actions が pytest / カバレッジ閾値 / `verify_pipeline.sh` 等を実行する。
pre-push フックは使わない（`git push` はフック待ちなく即完了する）。

### 任意: ローカルフル検証

GitHub Actions と同等の検査をローカルで先に回したい場合のみ `bash scripts/check.sh` を使う。
通常は push して GitHub Actions の結果を待てばよい。

`--quick` は開発中の途中確認のみ（pytest / verify_pipeline を省略）。

初回セットアップ:

```bash
bash scripts/setup-dev.sh
```

## check.sh が実行する内容（任意・GitHub Actions と同等）

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uvx pre-commit run --all-files`（zizmor / pinact / 基本フック含む）
4. `bash scripts/check_coverage.sh`（`pyproject.toml` の `fail_under` 未満で失敗）
5. `bash scripts/verify_pipeline.sh`（GitHub Actions と同じ end-to-end スモーク）

## データ取り扱い

- `data/` と `exports/` は `.gitignore` 済み。**絶対にコミットしない**。
- プロンプトバンク (`data/prompts/training_prompts.jsonl`) は
  `scripts/migrate_csv_to_jsonl.py` でローカル生成する。元 CSV のパスは引数で渡す。

## 実装完了の報告条件

- GitHub Actions（PR の workflow）が green（またはユーザーが PR URL を求めた場合は PR URL を返す）
- ローカルで `bash scripts/check.sh` を回した場合は exit 0

## Docker / joryu-up（コンテナ追加時）

インフラは **docker compose** + **`uv run joryu-up`** が唯一の起動経路とする。

**新しい compose サービス（コンテナ）を追加したら、必ず `joryu-up` からも起動されるように配線する。** 個別の `docker compose up <service>` や手動プロセス起動をユーザーに案内してはならない。

実装時は少なくとも次を更新する:

1. `docker-compose.yml` — サービス定義
2. `src/joryu/preflight.py` — `resolve_up_services` / `should_up_*` / `path_affects_service` / `services_to_build`
3. `src/joryu/readiness.py` — `wait_for_up_services`（health URL があれば ready 待ち）
4. `tests/test_preflight.py` / `tests/test_cli_up_down.py` / `tests/test_readiness.py` — TDD で起動対象・待機順序を固定

起動確認・ユーザーへの案内は **`uv run joryu-up`（必要なら `--detach`）** に統一する。例: MCP は `config.yaml` の `mcp.enabled` 時に `joryu-up` が `mcp` コンテナも up する。

## ロギング

- ライブラリ / CLI の診断出力は `print` ではなく `logging` を使う（`joryu.logging_config.setup_logging()` で stderr に出力）。
- `except` で例外を握るときは必ず `logger.exception(...)` または `logger.error(..., exc_info=True)` で traceback を残す。
- ruff `T20`（`print` 検出）を有効にしている。`src/joryu` 内に `print` を追加しない。
