# インタラクティブチャット UI

ダッシュボード `/chat` から、蒸留ジョブ非実行時に styles.yaml の全スタイルで並列対話し、
やり取りを `data/distilled/responses.jsonl` に `category="人間との対話"` として追記する機能。

## 起動

```bash
uv run joryu-up --detach
# ブラウザ: http://localhost:3000/chat
```

API は `http://localhost:8000/api/chat`（dashboard 経由は `/api/chat` プロキシ）。

## 操作フロー

1. ページ表示時にセッションが自動作成され、styles.yaml の列（prose / qa_short / dialog / report）が横並びで表示される。
2. **初回**: 画面下の単一 textarea から同一 prompt を全列へ並列送信。
3. **2 ターン目以降**: 各列の下部 textarea から、そのスタイルにだけ追加質問可能（履歴も列ごとに独立）。
4. ジョブ（蒸留 / 高品質抽出）が queued/running の間は送信不可（黄色バナー表示）。

## API エンドポイント

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/chat/styles` | スタイル一覧 |
| POST | `/api/chat/sessions` | セッション作成 |
| GET | `/api/chat/sessions/{id}` | 履歴取得 |
| DELETE | `/api/chat/sessions/{id}` | セッション破棄 |
| POST | `/api/chat/sessions/{id}/messages` | 初回: 全列並列 SSE |
| POST | `/api/chat/sessions/{id}/columns/{style_id}/messages` | 2 ターン目以降: 単列 SSE |

## SSE イベント

| event | data フィールド |
|-------|----------------|
| `token` | `column`, `delta` |
| `tool_call` | `column`, `call_id`, `name`, `arguments` |
| `tool_result` | `column`, `call_id`, `content` |
| `column_done` | `column`, `finish_reason`, `record_id` |
| `done` | `session_id` |
| `error` | `column?`, `message` |

## JSONL スキーマ拡張

既存 distill レコードに加え、チャット経由の行には次が付与される:

- `category`: 固定 `"人間との対話"`
- `session_id`: チャットセッション UUID
- `turn_index`: 列ごとのターン番号（0 起算）

蓄積確認: `/outputs?category=人間との対話`

## ジョブ排他

GPU 衝突回避のため、`JobRunner.running_id` がセットされている、または
ジョブストアに queued/running ジョブがある場合、送信系 API は **409** `{ "error": "job_active" }` を返す。

## 実装モジュール

- `src/joryu/chat/session.py` — インメモリセッション（TTL 30 分）
- `src/joryu/chat/streamer.py` — tool loop + 擬似トークン SSE
- `src/joryu/chat/persistence.py` — `build_chat_record()`
- `dashboard/src/app/chat/page.tsx` — UI
- `dashboard/src/lib/chat.ts` — SSE クライアント
