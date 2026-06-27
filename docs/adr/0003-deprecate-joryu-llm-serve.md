# ADR 0003: 旧 joryu-llm-serve ラッパの廃止

## ステータス

Accepted

## コンテキスト

PR #127 / #129 で Docker compose 本流は `vllm serve` (OpenAI 互換 `/v1/*`) に移行した。
それ以前は `joryu-llm-serve` CLI + `llm_server.py` (FastAPI `/v1/chat`) が独自 HTTP ラッパとして存在していた。

移行後も `config.yaml` の `vllm.backend: joryu-llm-serve` で手動切替可能な状態が残っていたが、
compose / `joryu-up` / ジョブ API 本流からは参照されず、テストと手動起動以外では使われていなかった。

## 決定

以下を削除する:

- `joryu-llm-serve` CLI エントリ (`pyproject.toml` `[project.scripts]`)
- `src/joryu/llm_server.py` / `src/joryu/cli/llm_serve.py`
- `vllm_client.VllmHttpClient` と `resolve_chat_client()` の `joryu-llm-serve` 分岐
- `config.yaml` の `vllm.backend: joryu-llm-serve` 選択肢

**残すもの:**

- `vllm.backend: inproc` — GPU 環境での in-process 推論テスト用
- `vllm.backend: vllm-serve` (既定) — compose が起動する本物 vLLM デーモン

## 影響

- 旧ラッパに依存していたローカル環境は `vllm.backend: vllm-serve` へ移行する必要がある
- `JORYU_VLLM_URL` による接続先指定は引き続き有効
- `config_hash` から `backend` はもともと除外されているため、蒸留 JSONL の再現性キーは変わらない

## 関連

- Issue #242 / 親 Epic #241
- ADR 0002 (streaming は `vllm-serve` のみ)
