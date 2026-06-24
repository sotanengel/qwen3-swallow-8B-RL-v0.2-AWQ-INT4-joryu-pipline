# SFT 側 (教師データ消費側) ガイド

このリポジトリで蒸留したデータを **別リポジトリ** で SFT に使うための手順。

## 1. ファイルの受け取り

`joryu-export --bundle-tar` の出力 (`exports/<timestamp>/`) または
`exports/<timestamp>.tar` を SFT 側にコピーする。

```
exports/20260621T140000Z/
├── responses.jsonl.zst   ← 蒸留データ本体 (zstd 圧縮)
├── meta.json             ← レコード数、モデル名、config_hash 等
└── SHA256SUMS            ← sha256sum -c 互換 (整合性検証)
```

## 2. 整合性検証

```bash
cd exports/20260621T140000Z
sha256sum -c SHA256SUMS
# responses.jsonl.zst: OK
# meta.json: OK
```

## 3. 展開

```bash
zstd -d responses.jsonl.zst -o responses.jsonl
```

Python から直接読む場合は展開不要:

```python
import json
import zstandard as zstd

with open("responses.jsonl.zst", "rb") as cf:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(cf) as reader:
        text = reader.read().decode("utf-8")
for line in text.splitlines():
    record = json.loads(line)
    # record["prompt"], record["answer"], record["mode"], record["sampling"], ...
```

## 4. レコードスキーマ

```json
{
  "prompt": "...",
  "category": "国語",
  "style_id": "formal_essay",
  "mode": "thinking",
  "system_prompt": "あなたは丁寧で正確な日本語アシスタントです。...",
  "sampling": {
    "temperature": 0.6, "top_p": 0.95, "top_k": 20,
    "max_tokens": 384, "repetition_penalty": 1.05
  },
  "thinking_trace": "<thinking 内容>",
  "reasoning": "<thinking 内容>",
  "answer": "<最終回答>",
  "tools": [],
  "tool_ids_requested": [],
  "tool_calls": [],
  "turns": [],
  "model": "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4",
  "config_hash": "sha256-...",
  "created_at": "2026-06-21T14:00:00.000000+00:00"
}
```

非推論モードの場合 `thinking_trace` は `null`、`reasoning` は空文字列。

### ツール付きレコードの再構築

レコード内 `tools` フィールドだけで chat_template 入力を再構築できる:

```python
from joryu.record_replay import rebuild_chat_template_inputs

inputs = rebuild_chat_template_inputs(record)
# inputs["messages"], inputs["tools"] を apply_chat_template に渡す
```

`tool_calls` はモデルが出力した `<tool_call>{...}</tool_call>` のパース結果。
`turns` はマルチターン tool 実行ループ有効時の履歴（未使用時は空配列）。

## 5. SFT データフォーマットへの変換例

### ChatML (Qwen3 系)

```python
def to_chatml(record):
    return [
        {"role": "system", "content": record["system_prompt"]},
        {"role": "user", "content": record["prompt"]},
        {"role": "assistant", "content": record["answer"]},
    ]
```

### Unsloth / TRL 用 messages フォーマット

上の ChatML をそのまま `messages` 列に入れるだけ。thinking を学習に含めたい場合は
`assistant` 内容の冒頭に `<think>{thinking_trace}</think>` を再挿入する。

### フィルタリング推奨

- 同一 `(prompt, sampling.temperature, sampling.top_p, mode)` 重複は `joryu` 側で防止済み
  (`config_hash` をキーにスキップ) だが、複数バッチを結合するときは `prompt + sampling`
  で再重複排除すると安心。
- `answer` が極端に短い (例: 10 文字未満) レコードは品質が低い可能性が高い。

## 6. config_hash で蒸留設定を再現

```python
import json

with open("meta.json") as f:
    meta = json.load(f)
print(meta["config_hash"])      # sha256-...
print(meta["model"])            # Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4
print(meta["records"])          # N
print(meta["time_range"])       # {first, last}
```

`config_hash` が同じ複数のエクスポートは、同じ `config.yaml` で蒸留されたものとして
連結して構わない。異なるハッシュをまとめる場合は学習側で混在を意識すること。
