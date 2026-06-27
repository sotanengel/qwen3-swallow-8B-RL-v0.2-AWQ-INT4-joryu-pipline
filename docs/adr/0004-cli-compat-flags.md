# ADR 0004: CLI 互換フラグの整理

## ステータス

Accepted

## コンテキスト

Issue #244 で README / コード上の後方互換フラグを棚卸しした。

- `--mode` (蒸留 thinking/nothinking 切替): Issue #94 で既に削除済み
- `joryu-up --full`: 引数なし `joryu-up` と完全に同一の冗長 alias
- `joryu-serve`: `joryu-up --frontend-only` の短縮 alias

## 決定

| フラグ / エイリアス | 判断 | 理由 |
|---|---|---|
| `--mode` | 廃止済み (変更なし) | #94 で CLI から削除 |
| `joryu-up --full` | **削除** | `resolve_up_services()` で default と同一 |
| `joryu-serve` | **保持** | frontend-only 起動の低コスト alias |

`joryu-up --full` の代替: 引数なし `uv run joryu-up`

## 影響

- 既存スクリプトで `--full` を使っていた場合はフラグを外すだけで同等

## 関連

- Issue #244 / 親 Epic #241
