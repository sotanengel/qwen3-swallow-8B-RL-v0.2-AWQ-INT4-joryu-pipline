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

## 非機能要件

- **VRAM**: 8GB (RTX 3060 Ti) 想定。`num_ctx=512` / `num_predict=384`
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
