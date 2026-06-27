# 健全性スクリーニング (Epic #305)

蒸留データの **テキスト健全性** を `joryu-curate --screening` で評価する手順。

## 前提

- 評価対象: Qwen3 Swallow 蒸留 JSONL (`prompt` / `answer` / `thinking_trace`)
- 既定 Judge: **Llama-3.1-Swallow-8B-Instruct-v0.5** (Qwen3 セルフバイアス回避)
- 実行環境目安: RTX 3060 Ti (VRAM 8GB) + Q4_K_M GGUF

## Llama-Swallow judge の起動 (llama-server)

1. GGUF をダウンロード (例: Hugging Face から Q4_K_M)
2. llama.cpp の `llama-server` を起動:

```bash
llama-server \
  --model /path/to/Llama-3.1-Swallow-8B-Instruct-v0.5-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 4096 \
  --n-gpu-layers 99
```

3. `config.yaml` の `curate.screening.judge.base_url` が `http://localhost:8080` を指すことを確認

## スクリーニング実行

```bash
uv run joryu-curate --screening --detach
# または入力/出力を明示
uv run joryu-curate --screening --src data/distilled/responses.jsonl --dst data/curated/screening_run
```

CI / オフライン検証:

```bash
JORYU_CURATE_FAKE_JUDGE=1 uv run joryu-curate --screening --no-resume ...
```

## 出力

| ファイル | 内容 |
|---------|------|
| `screening.ok.jsonl` | OK ラベル |
| `screening.review.jsonl` | 人手レビュー対象 |
| `screening.ng.jsonl` | NG ラベル |
| `scores.jsonl` | 全件スコア + `screening_label` |
| `responses.high_quality.jsonl` | 後方互換 (OK と同一) |

## Judge の切り替え

```bash
uv run joryu-curate --screening \
  --judge-provider openai_compat \
  --judge-base-url http://localhost:8100 \
  --judge-model Llama-3.1-Swallow-8B-Instruct-v0.5
```

`--judge-provider vllm` で常駐 vLLM デーモン経路も利用可能。

## セルフバイアス比較

```bash
uv run python scripts/judge_bias_check.py --scores data/curated/<run>/scores.jsonl --sample 50
```

## VRAM / OOM 対策

- think テキストは評価時に冒頭/末尾各 500 字に truncate
- `max_tokens` は judge クライアントで 256 に制限
- 最大長サンプルで事前に 1 件試行してからバッチ実行

## プロンプトバンク (Epic #313)

プロンプトシード (`training_prompts.jsonl`) を **LLM 単体**でスクリーニングする。
ルールシグナル (CTRL-CHAR / END-WELL 等) は適用しない。

```bash
JORYU_CURATE_FAKE_JUDGE=1 uv run joryu-curate \
  --screening --prompt-bank \
  --src data/prompts/training_prompts.jsonl \
  --dst data/curated/prompt_screening
```

詳細: [seed_gen.md](seed_gen.md)
