# Agent 向け開発ルール

## CI ゲート（必須・例外なし）

**`git commit` または PR 作成の前に、必ず次を実行し、全て成功してから進める。**

```bash
bash scripts/check.sh
```

`pytest` だけ、`ruff` だけ、など部分的な検査で完了報告してはならない。

初回セットアップ:

```bash
bash scripts/setup-dev.sh
```

## check.sh が実行する内容

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uvx pre-commit run --all-files`（zizmor / pinact / 基本フック含む）
4. `bash scripts/check_coverage.sh`（`pyproject.toml` の `fail_under` 未満で失敗）
5. `bash scripts/verify_pipeline.sh`（CI と同じ end-to-end スモーク）

`--quick` は開発中の途中確認のみ。PR・コミット前では使用禁止。`--quick` でも **pre-commit（JSONL lint / ruff / zizmor 等）は実行される**が、`pytest` カバレッジと `verify_pipeline.sh` は省略される。

## pre-commit / pre-push フック

`setup-dev.sh` が `pre-commit` と `pre-push` を登録する。
`--no-verify` でフックを迂回することは禁止。

## データ取り扱い

- `data/` と `exports/` は `.gitignore` 済み。**絶対にコミットしない**。
- プロンプトバンク (`data/prompts/training_prompts.jsonl`) は
  `scripts/migrate_csv_to_jsonl.py` でローカル生成する。元 CSV のパスは引数で渡す。

## 実装完了の報告条件

- `bash scripts/check.sh` が exit 0
- ユーザーが PR を求めた場合は PR URL を返す

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
