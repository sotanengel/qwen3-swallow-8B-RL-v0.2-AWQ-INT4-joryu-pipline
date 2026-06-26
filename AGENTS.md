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

`--quick` は開発中の途中確認のみ。PR・コミット前では使用禁止。

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
