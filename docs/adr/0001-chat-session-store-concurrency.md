# ADR 0001: ChatSessionStore の並行整合

## ステータス

Accepted

## コンテキスト

`ChatSessionStore` は FastAPI プロセス内のインメモリ dict (`_sessions`) でセッションを保持する。TTL 30 分で期限切れ purge する。

現状:

- ロックなし
- シングルワーカー (uvicorn 1 worker) + asyncio イベントループ前提
- 同期 CRUD (`create` / `get` / `delete`) と非同期 SSE ストリーミングが同一プロセス内で共存

## 決定

**現契約では `asyncio.Lock` 等の明示ロックは導入しない。**

理由:

1. FastAPI の async ルートは単一イベントループ上で協調的に動作し、`ChatSessionStore` の操作はいずれも短い同期処理である。
2. ストリーミング中の `stream_column_turn` は `column.messages` を mutate するが、同一 `session_id` に対する並行 POST は UI 側で送信中フラグにより抑制されている。
3. `delete` と streaming の競合は、delete 後に `get` が None を返すため新規リクエストは 404 になる。進行中ストリームは session オブジェクト参照を保持するため完走するが、結果は当該プロセス内の短命オブジェクトへの書き込みに留まり、他リクエストからは参照されない。

## マルチワーカー

`gunicorn -w 2` 等で複数ワーカーを起動した場合、**`_sessions` はプロセス間で共有されない**。これは現仕様の制限として許容する。

- セッション作成とメッセージ POST が異なるワーカーに振られると 404 になる
- 本番デプロイでは uvicorn worker=1 を前提とする

## 競合シナリオ

| シナリオ | 結果 | 許容 |
|---------|------|------|
| TTL purge と get | purge 後 get は None | 可 |
| delete と streaming | ストリームは完走、以降 get は 404 | 可 |
| 同一 session への並行 POST | UI が抑制。API 単体では未保証 | 現状可 (将来 Issue 化可) |

## 将来

以下が必要になった場合は別 Issue で `asyncio.Lock` または Redis 等の外部ストアを検討する:

- 同一 session への API レベル並行 POST 禁止
- マルチワーカー対応
- セッション永続化
