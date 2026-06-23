# joryu 蒸留パイプライン 要件定義

## 目的

`Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4` をローカルで蒸留し、JSONL データを別リポジトリの
SFT 教師データとして再利用可能な形で配布する。

## 利用シーン

1. **オフライン蒸留**: 4,000+ 個の日本語プロンプトに対する高品質な回答を生成する。
2. **文体・サンプリング掃き出し**: 同一プロンプトを文体 / temperature / top_p で
   直積展開して多様なバリアントを生成する。
3. **推論/非推論モード切替**: thinking と nothinking で得られるデータを使い分ける。
4. **データ配布**: zstd 圧縮 + SHA256 + meta.json で別リポジトリへ持ち運ぶ。
5. **品質確認**: 検索 + 分布のダッシュボードで蒸留データの偏りを目視する。

## 機能要件

| ID | 要件 | 実装 |
|---|---|---|
| R-01 | プロンプト 1 行ごとに `mode` / `sampling` / `system_prompt` 上書きできる | [src/joryu/prompt_bank.py](../src/joryu/prompt_bank.py) |
| R-02 | 推論モード (`<think>...</think>` 含む) と非推論モードを切替できる | [src/joryu/distill.py](../src/joryu/distill.py), [src/joryu/vllm_client.py](../src/joryu/vllm_client.py) |
| R-03 | 中断・再開が安全 (既処理レコードはスキップ) | [src/joryu/progress.py](../src/joryu/progress.py), [src/joryu/writer.py](../src/joryu/writer.py) |
| R-04 | 実行コマンドは簡略 (count / duration のみで起動可能) | [src/joryu/cli/distill.py](../src/joryu/cli/distill.py) |
| R-05 | Windows でも実行できる (Docker 自動委譲) | [src/joryu/docker_delegate.py](../src/joryu/docker_delegate.py) |
| R-06 | 出力データは圧縮 + ハッシュ付きで持ち運べる | [src/joryu/export.py](../src/joryu/export.py) |
| R-07 | データ品質を可視化できる (検索 + 分布) | [dashboard/](../dashboard/) |
| R-08 | TDD: ruff / pre-commit / pytest / CI で常時担保 | [.github/workflows/ci.yml](../.github/workflows/ci.yml) |
| R-09 | 既存 JSONL (生 / `.zst`) をストリーミングで読み込みレコード単位評価 | [src/joryu/curate/loader.py](../src/joryu/curate/loader.py) |
| R-10 | 統計シグナル (LEN-A/LEN-T/RATIO-TA/TRUNC/THINK-TAG/LANG-JA/REPEAT-NG/REPEAT-CHAR/DUP-GLOB) を LLM 無しで計算 | [src/joryu/curate/signals/stat.py](../src/joryu/curate/signals/stat.py) |
| R-11 | joryu モデルを judge として呼び出し LLM-RUBRIC を付与 | [src/joryu/curate/signals/llm_judge.py](../src/joryu/curate/signals/llm_judge.py), [src/joryu/curate/judge_client.py](../src/joryu/curate/judge_client.py) |
| R-13 | シグナルを重み付き合成し threshold / top-k / keep-rate で抽出 | [src/joryu/curate/scoring.py](../src/joryu/curate/scoring.py) |
| R-14 | 採用 / 棄却を別ファイルに分離、棄却には `rejected_by` 付与 | [src/joryu/curate/writer.py](../src/joryu/curate/writer.py) |
| R-15 | CLI `joryu-curate` を提供 | [src/joryu/cli/curate.py](../src/joryu/cli/curate.py) |
| R-17 | `curation_meta.json` に入力 SHA256 / 設定ハッシュ 3 層 / コミット SHA を記録 | [src/joryu/curate/meta.py](../src/joryu/curate/meta.py) |
| R-18 | ダッシュボードに採用率・スコア分布・棄却理由 Top-N を表示 | [dashboard/src/app/curation/page.tsx](../dashboard/src/app/curation/page.tsx) + [src/joryu/curate/stats.py](../src/joryu/curate/stats.py) |
| R-19 | Fake judge クライアントで CPU CI が回ること | [tests/curate/](../tests/curate/) |

> R-12 (best-of-N), R-16 (resume 細部), R-20〜R-25 (差分実行キャッシュ / signal バージョニング / MinHash 永続化) は follow-up PR で対応。本 PR には scaffold (`record_hash`, `signal_versions` フィールド) のみ含む。

## 非機能要件

- **VRAM**: 8GB (RTX 3060 Ti) 想定。`num_ctx=2048` / `num_predict=1024`（`scripts/probe_vllm_limits.py` で OOM 時自動降格）
- **CPU CI**: vLLM は遅延 import + Fake クライアントでテスト
- **再現性**: 出力レコードに `config_hash` と effective `sampling` / `mode` を記録
- **データ非コミット**: `data/` / `exports/` / `models/` は `.gitignore`

## 制約

- vLLM は Linux + CUDA のみ動作。Windows ネイティブでは Docker 委譲必須。
- `awq_marlin` 量子化で `dtype: float16` を使うと token=0 を吐くバグ (`bfloat16` 必須)。
- `VLLM_USE_FLASHINFER_SAMPLER=0` (CUDA devel ではなく runtime ベースの image を使うため)。

## 既定値とプリセット

- 既定設定: [config.yaml](../config.yaml)
- 非推論プリセット: [config.nothinking.yaml](../config.nothinking.yaml)
- 文体プリセット: [styles.yaml](../styles.yaml)
