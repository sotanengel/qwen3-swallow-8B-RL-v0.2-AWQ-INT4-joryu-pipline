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
   distill.py ─── chat_via_template ───▶ resolve_chat_client() ──┬──▶ VllmServeClient → vllm serve :8100/v1 (既定)
              │         ▲                      │                 └──▶ VllmClient (in-process GPU)
              │         └── tool_loop 時: tool_executor.py (Stub/Registry)
              │   ◄── enable_thinking で <think> 切替 ──┘
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
                          jobs/runner → distill (JORYU_VLLM_URL 時は api 内 subprocess)
                                    │
                                    ▼ HTTP /v1/chat/completions (OpenAI 互換)
                          vllm serve (常駐) :8100
                                    │
                                    ▼
                          data/jobs/*.json (状態・ログ)
```

## レイヤー再設計 (#249)

```
Entry (cli/*, api/routes/*)
        │
        ▼
DependencyContainer (container.py + config_resolver.py)
        │
        ├── DistillPipeline (distill/ Stage 連結)
        │        └── ToolCallPipeline (tool_pipeline/)
        ├── CuratePipeline (curate/pipeline.py + CurateStage)
        └── RunnerStrategyFactory (jobs/strategy.py)

Infrastructure
  ├── joryu.vllm/     HttpVllmBase, ChatClient Protocol, ToolCallParser
  ├── joryu.streaming/ SSEEncoder / SSEDecoder
  └── joryu.schema/   Pydantic version 付き YAML 検証

Dashboard: npm run gen:types → dashboard/src/types/api.ts (OpenAPI 同期)
```

## レイヤーごとの責務

| レイヤー | 入力 | 出力 | 主モジュール |
|---|---|---|---|
| 設定 | config.yaml / styles.yaml | dataclass | config.py / styles.py |
| プロンプト読込 | JSONL | `PromptRow[]` | prompt_bank.py |
| バリアント展開 | row + 直積引数 | `DistillVariant[]` | variants.py |
| 推論 | messages + sampling | `(thinking, answer)` | joryu.vllm/ (shim: vllm_client.py) |
| ループ制御 | variants, deadline, count | 書き込んだ件数 | distill/pipeline.py (DistillPipeline) |
| tool loop | messages + tools | ChatResult + turns | tool_pipeline/pipeline.py |
| 進捗 | iteration ごと | stderr 表示 | progress_reporter.py |
| 出力 | record dict | JSONL 1 行 | writer.py |
| 再開 | 既存 JSONL | 処理済 run キー集合 | progress.py |
| 配布 | JSONL | `.zst` / `meta.json` / `SHA256SUMS` / `.tar` | export.py |
| 統計 | JSONL | dashboard 用 JSON | stats.py |
| Docker 委譲 | Windows ネイティブ呼び出し | `docker run` 実行 | docker_delegate.py |
| ジョブ API | HTTP POST ジョブ spec | queued/running 状態 + ログ | jobs/ + api/ |
| ジョブ実行 | spec | 蒸留 subprocess (daemon 経由 or GPU docker run) | jobs/runner.py + jobs/strategy.py |
| vLLM 常駐 | config.yaml | HTTP `/health`, OpenAI `/v1/*` | docker-compose (`vllm serve`) |

## CLI 構成

| コマンド | 役割 |
|---|---|
| `joryu-distill` | 蒸留ループ実行 (Windows なら auto Docker) |
| `joryu-export` | zstd 圧縮 + meta + SHA256 + tar |
| `joryu-stats` | dashboard JSON 生成 (`--curation <run_dir>` で curation.json も) |
| `joryu-curate` | 蒸留 JSONL から高品質サブセットを抽出 |
| `joryu-api` | 蒸留ジョブ REST API (FastAPI, :8000) |
| `joryu-up` | git 差分 → `compose build` → `compose up` (既定: dashboard + api + joryu)。`--detach` 時 ready 待ち |
| `joryu-up --force` | ディスク preflight をスキップ |
| `joryu-serve` | `joryu-up --frontend-only` の互換エイリアス |

## 再現性キー

出力レコードに含めるのは:

- `model` (= モデル名)
- `sampling` (実際に使われた値)
- `system_prompt`
- `config_hash` (`config.yaml` 全体の SHA256)

下流 SFT は config_hash で蒸留時の設定を一意に特定できる。

## tool calling 品質フロー (#109)

compass 調査に基づき、蒸留〜curate で次の責務分担を取る。

```
vLLM 生成
    │
    ▼
tool_calls.py (+ raw_completion 診断)     ← parser ロスト検出
    │
    ▼
tool_intent.py → tool_call_recovery.py    ← intent あり & calls 空 → 強制リトライ
    │                                         (optional: no_think_fallback)
    ▼
responses.jsonl (+ tool_call_recovery メタ)
    │
    ▼
curate/signals/tool_use.py                ← TOOL-PLAN / TOOL-CLAIM で hard reject
    │
    ▼
responses.high_quality.jsonl              ← SFT 教師データ
```

| 段階 | 救済するもの | 救済しないもの |
|---|---|---|
| 蒸留 (recovery) | thinking 内 intent + calls 空、raw に `<tool_call>` 残骸 | モデルが tool 系列を一切生成しないケース |
| curate (TOOL-*) | 計画のみ / 捏造応答 | 低品質だが tool call は正しいケース |
| スコープ外 | — | 教師能力そのもの（Swallow 未学習）→ 段階3で別モデル or post-training |

**判断閾値**: curate 通過率が 40% 未満なら教師変更を優先。stats の
`tool_planned_but_not_called_rate` / `no_think_fallback_rescued_count` で A/B 計測する。

## データ品質ガード (#220)

`data/distilled/responses.jsonl` レビューで観測された失敗パターン A〜I と、各レイヤでの抑止策。

| ID | 失敗パターン | 抑止レイヤ | 実装 |
|---|---|---|---|
| A | answer に raw JSON tool_call 漏出 | 出力パーサ | [`completion_normalize.py`](../src/joryu/completion_normalize.py), [`vllm_stream_client.py`](../src/joryu/vllm_stream_client.py) — [#229](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/229) |
| B | ツール未呼び出しで温度等を捏造 | system プロンプト + R-10 | [`system_prompt.py`](../src/joryu/system_prompt.py), R-10 `FACT-HALL` — [#231](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/231) |
| C | 「仮想データ」と明示しつつ表を捏造 | system プロンプト + R-10 | factual guard, R-10 `VIRT-DATA` — [#231](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/231) |
| D | thinking に英語メタ命令断片 | 出力パーサ | `sanitize_thinking_trace()` — [#229](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/229) |
| E | answer 空 / thinking 途中打切り | チャット再生成 | [`chat/generate_retry.py`](../src/joryu/chat/generate_retry.py) — [#232](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/232) |
| F | 2 周目以降 JSON 再生成で tool ループ不入 | tool ループ + パーサ | [`tool_loop.py`](../src/joryu/chat/tool_loop.py) + `normalize_chat_result` — [#233](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/233) |
| G | 同一プロンプトの過剰重複 | JSONL 追記前 | [`prompt_dedup.py`](../src/joryu/prompt_dedup.py) — [#235](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/235) |
| H | `suspected_unparsed_tool_calls` 常に空 | 診断 + R-10 | `normalize_chat_result`, R-10 `TOOL-LEAK` — [#230](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/230) |
| I | prose 指示でも JSON / 箇条書き | system プロンプト順 + R-10 | style を最後に配置, R-10 `STYLE-FMT` — [#234](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/234) |

### レイヤ別責務マトリクス

| レイヤ | 検出 (reject) | 修正 (rewrite) |
|---|---|---|
| system プロンプト合成 | — | factual guard, tool hint, style 末尾配置 |
| chat_template / vLLM | — | （モデル出力形式はパーサ側で救済） |
| 出力パーサ (`completion_normalize`) | suspected hints | bare JSON → tool_calls, thinking サニタイズ |
| tool ループ | — | 各ターン normalize + recovery |
| チャット retry | 空 answer 時 JSONL 非追記 | 最大 2 回再生成 |
| R-10 stat | TOOL-LEAK, FACT-HALL, VIRT-DATA, STYLE-FMT | — |
| R-11 LLM judge | 既存 rubric | — |

### 追加 R-10 ルール

| Code | hard_reject 条件 |
|---|---|
| `TOOL-LEAK` | `suspected_unparsed_tool_calls` 非空 |
| `FACT-HALL` | tools あり & tool_calls 空 & answer に `\d+℃` 等 |
| `VIRT-DATA` | answer に `仮想データ` / `架空` / `推測値` / `（例）` |
| `STYLE-FMT` | prose/qa_short/dialog で markdown 記号・箇条書き |

CI 検証: [`scripts/verify_distill_quality.sh`](../scripts/verify_distill_quality.sh)（[`verify_pipeline.sh`](../scripts/verify_pipeline.sh) から呼び出し）。回帰テスト: [`tests/test_distill_quality_regression.py`](../tests/test_distill_quality_regression.py) — [#237](https://github.com/sotanengel/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline/issues/237).

## マルチ LLM ModelProfile FSM (8GB GPU 排他)

`config.yaml` の `models.profiles[]` が compose service / port / health / kind の単一情報源。
`ModelOrchestrator` (API プロセス内シングルトン) が FSM で GPU profile を排他切替する。

| Profile | Compose service | 用途 |
|---|---|---|
| `distill` | `joryu` (vLLM Qwen3) | 蒸留・チャット |
| `seed_gen` | `joryu-seed` (vLLM Qwen2.5) | プロンプト生成 |
| `screening` | `joryu-judge` (llama-server GGUF) | 健全性 judge |

- `joryu-up` は `--profile always --profile distill` で api/dashboard + 蒸留 LLM を起動
- seed_gen / screening はジョブ enqueue 時に lazy 起動 (`JobRunner.ensure_profile`)
- 状態は `GET /api/system/models` と SSE `/api/system/models/stream` で配信
- 詳細: [ADR-0005](adr/0005-multi-llm-profiles.md)
