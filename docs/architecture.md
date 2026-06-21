# joryu アーキテクチャ

```
┌──────────────────────────────────────────────────────────────────┐
│                        joryu pipeline                            │
└──────────────────────────────────────────────────────────────────┘

config.yaml ──┐
styles.yaml ──┤
              ▼
   prompt_bank.py ◄── data/prompts/*.jsonl (1 行 1 prompt + row overrides)
              │
              ▼
   variants.py (style × temperature × top_p の直積)
              │
              ▼
   distill.py ─── chat_via_template ───▶ vllm_client.py ──▶ vLLM (GPU)
              │                                              │
              │   ◄── enable_thinking で <think> 切替 ──────┘
              │
              ▼
   writer.py (resume-safe JSONL append, ensure_ascii=False)
              │
              ▼
   data/distilled/responses.jsonl
              │
       ┌──────┴──────────────────┐
       ▼                         ▼
   export.py                  stats.py
   (zstd + SHA256             (category / mode /
    + meta.json + tar)         length / sampling /
       │                       timeline ヒストグラム)
       ▼                         ▼
   exports/<ts>/             dashboard/public/stats.json
   responses.jsonl.zst              │
                                    ▼
                          Next.js (recharts, 検索)
                          http://localhost:3000
```

## レイヤーごとの責務

| レイヤー | 入力 | 出力 | 主モジュール |
|---|---|---|---|
| 設定 | config.yaml / styles.yaml | dataclass | config.py / styles.py |
| プロンプト読込 | JSONL | `PromptRow[]` | prompt_bank.py |
| バリアント展開 | row + 直積引数 | `DistillVariant[]` | variants.py |
| 推論 | messages + sampling | `(thinking, answer)` | vllm_client.py |
| ループ制御 | variants, deadline, count | 書き込んだ件数 | distill.py |
| 進捗 | iteration ごと | stderr 表示 | progress_reporter.py |
| 出力 | record dict | JSONL 1 行 | writer.py |
| 再開 | 既存 JSONL | 処理済 run キー集合 | progress.py |
| 配布 | JSONL | `.zst` / `meta.json` / `SHA256SUMS` / `.tar` | export.py |
| 統計 | JSONL | dashboard 用 JSON | stats.py |
| Docker 委譲 | Windows ネイティブ呼び出し | `docker run` 実行 | docker_delegate.py |

## CLI 構成

| コマンド | 役割 |
|---|---|
| `joryu-distill` | 蒸留ループ実行 (Windows なら auto Docker) |
| `joryu-export` | zstd 圧縮 + meta + SHA256 + tar |
| `joryu-stats` | dashboard JSON 生成 |
| `joryu-up` | 既定: `docker compose up dashboard --build` |
| `joryu-up --full` | `docker compose up --build` (joryu + dashboard) |
| `joryu-serve` | `joryu-up --frontend-only` の互換エイリアス |

## 再現性キー

出力レコードに含めるのは:

- `model` (= モデル名)
- `mode` (`thinking` or `nothinking`)
- `sampling` (実際に使われた値)
- `system_prompt`
- `config_hash` (`config.yaml` 全体の SHA256)

下流 SFT は config_hash で蒸留時の設定を一意に特定できる。
