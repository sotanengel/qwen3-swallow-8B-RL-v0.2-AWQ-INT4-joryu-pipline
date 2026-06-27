# ADR-0002: チャット真の token streaming

## Status

Accepted

## Context

4 列チャット (`POST /api/chat/sessions/{id}/messages`) は vLLM 推論完了後に answer を 8 文字 chunk で SSE 転送していた。
`max_num_seqs=1` と同期 `chat_via_template()` により asyncio がブロックされ、初回 token まで数分の無音時間が発生していた。
UI は `isStreaming && streamingText` のときのみ表示するため、推論中はユーザメッセージだけが見えた。

## Decision

1. **vllm-serve backend** 向けに `VllmServeStreamClient` を追加し、OpenAI 互換 `POST /v1/chat/completions` に `stream=true` で接続する。
2. `ToolLoopRunner` は streaming client がある場合、delta を即時 `token` SSE として yield する。ない場合は `asyncio.to_thread()` で同期呼び出しし、従来 chunk 分割にフォールバックする。
3. 進捗 SSE として `column_start` / `turn_start` を追加し、推論開始を即座に UI へ通知する。
4. Dashboard は `isStreaming && !streamingText` のとき「考え中…」スピナーを表示する。
5. 4 列並列 (`merge_streams`)、tools schema、先行完了列の `column_done` 即時反映は維持する。

## Consequences

- `backend: vllm-serve` 以外 (`inproc`) は streaming 非対応のまま。イベントループブロックは `asyncio.to_thread` で緩和。
- `httpx` を api extra 依存に追加。
- `recover_tool_call` は streaming 完了後の `ChatResult` に対して従来どおり実行。

## Alternatives considered

- 列直列化: ユーザー要望により並列維持。
- チャットから tools 除去: ユーザー要望により tools 維持。
