# joryu アーキテクチャ

```
┌──────────────────────────────────────────────────────────────────┐
│                        joryu pipeline                            │
└──────────────────────────────────────────────────────────────────┘

config.yaml ──┐
styles.yaml ──┤
tools.yaml ───┤
              ▼
   prompt_bank.py ◄── data/prompts/*.jsonl (1 行 1 prompt + row overrides + tool_ids)
              │
              ▼
   tools.py (tool_ids → OpenAI schema 解決)
              │
              ▼
   variants.py (style × temperature × top_p × mode の直積)
              │
              ▼
   distill.py ─── chat_via_template ───▶ vllm_client.py ──▶ vLLM (GPU)
              │         ▲                      │
              │         └── tool_loop 時: tool_executor.py (Stub/Registry)
              │   ◄── enable_thinking で <think> 切替 (auto は kwargs 省略) ──┘
              │
              ▼
   writer.py (resume-safe JSONL append, ensure_ascii=False)
              │
              ▼
   data/distilled/responses.jsonl
              │
       ┌──────┴──────────────────┬─────────────────┐
       ▼                         ▼                 ▼
   export.py                  stats.py        curate/loader.py
   (zstd + SHA256             (category /         │
    + meta.json + tar)         mode / length /    ▼
       │                       sampling /     curate/signals/stat.py (R-10)
       │                       timeline)          │
       ▼                                          ▼ (第一段通過分のみ)
   exports/<ts>/                              curate/signals/llm_judge.py (R-11)
   responses.jsonl.zst                            │
                                                  ▼
                                              curate/scoring.py + writer.py
                                                  │
                                       ┌──────────┴──────────┐
                                       ▼                     ▼
                                   responses.high_quality   responses.rejected
                                   .jsonl                   .jsonl (+ rejected_by)
                                       │
                                       ▼
                                   scores.jsonl + curation_meta.json
                                       │
                                       ▼
                          dashboard/public/{stats,curation}.json
                                    │
                                    ▼
                          Next.js (recharts, 検索, /jobs, /curation)
                          http://localhost:3000
                                    ▲
                                    │ POST/GET /api/jobs
                                    │
                          joryu-api (FastAPI) :8000
                                    │
                                    ▼
                          jobs/runner → docker compose run joryu
                                    │
                                    ▼
                          data/jobs/*.json (状態・ログ)
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
| ジョブ API | HTTP POST ジョブ spec | queued/running 状態 + ログ | jobs/ + api/ |
| ジョブ実行 | spec | GPU 蒸留 subprocess | jobs/runner.py |

## CLI 構成

| コマンド | 役割 |
|---|---|
| `joryu-distill` | 蒸留ループ実行 (Windows なら auto Docker) |
| `joryu-export` | zstd 圧縮 + meta + SHA256 + tar |
| `joryu-stats` | dashboard JSON 生成 (`--curation <run_dir>` で curation.json も) |
| `joryu-curate` | 蒸留 JSONL から高品質サブセットを抽出 |
| `joryu-api` | 蒸留ジョブ REST API (FastAPI, :8000) |
| `joryu-up` | git 差分 → `compose build` → `compose up` (既定: dashboard + api)。API ジョブ用 `joryu:latest` は初回・差分・未作成時に build |
| `joryu-up --full` | dashboard + api + joryu を up、差分がある方だけ build |
| `joryu-up --force` | ディスク preflight をスキップ |
| `joryu-serve` | `joryu-up --frontend-only` の互換エイリアス |

## 再現性キー

出力レコードに含めるのは:

- `model` (= モデル名)
- `mode` (`thinking` / `nothinking` / `auto` — 要求値)
- `effective_mode` (`thinking` / `nothinking` — 実際の出力に基づく実測値)
- `sampling` (実際に使われた値)
- `system_prompt`
- `config_hash` (`config.yaml` 全体の SHA256)

下流 SFT は config_hash で蒸留時の設定を一意に特定できる。
