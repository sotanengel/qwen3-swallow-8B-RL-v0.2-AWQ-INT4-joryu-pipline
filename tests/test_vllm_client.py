"""vllm_client.py: thin wrapper のメッセージ整形・thinking 解析・SamplingParams 構築。

実 vLLM はロードせず、内部メソッドのユニットテストと FakeVllmClient 仕様の確認のみ。
"""

from __future__ import annotations

import re

import pytest

from joryu.config import Config
from joryu.vllm_client import (
    SupportsChat,
    VllmClient,
    extract_thinking,
)


def test_extract_thinking_handles_thinking_block() -> None:
    text = "<think>これは思考</think>\n答えはこちら。"
    thinking, answer = extract_thinking(text)
    assert thinking == "これは思考"
    assert answer == "答えはこちら。"


def test_extract_thinking_no_block() -> None:
    text = "プレーンな出力"
    thinking, answer = extract_thinking(text)
    assert thinking is None
    assert answer == "プレーンな出力"


def test_extract_thinking_multiline() -> None:
    text = "<think>line1\nline2</think>本文"
    thinking, answer = extract_thinking(text)
    assert thinking is not None
    assert "line1" in thinking and "line2" in thinking
    assert answer == "本文"


def test_vllm_client_from_config_does_not_load() -> None:
    # コンストラクタは vllm を import しないことを保証 (CI で vllm 未インストールでも構築可能)
    cfg = Config()
    client = VllmClient.from_config(cfg.model, cfg.vllm)
    assert client._model_path == cfg.vllm.model_path
    assert client._dtype == cfg.vllm.dtype
    assert client._quantization == cfg.vllm.quantization
    assert client._max_tokens == cfg.model.num_predict
    assert client._max_model_len == cfg.model.num_ctx
    assert client._llm is None


def test_supports_chat_protocol_signature() -> None:
    # ダミー実装が SupportsChat を満たすことを確認 (Protocol チェック)
    class _Fake:
        def chat_via_template(
            self,
            messages: list[dict[str, str]],
            *,
            enable_thinking: bool = True,
            **sampling_overrides: object,
        ) -> tuple[str | None, str]:
            return None, "ok"

    fake: SupportsChat = _Fake()
    thinking, answer = fake.chat_via_template([{"role": "user", "content": "hi"}])
    assert thinking is None
    assert answer == "ok"


def test_vllm_client_chat_via_template_requires_vllm() -> None:
    # 実際の chat_via_template 呼び出しは _load を経由するため、
    # vllm 未インストール環境では ImportError になることを確認。
    cfg = Config()
    client = VllmClient.from_config(cfg.model, cfg.vllm)
    try:
        import vllm  # noqa: F401

        pytest.skip("vllm がインストールされているためテストをスキップ")
    except ImportError:
        pass

    with pytest.raises(ImportError, match=re.compile("vllm", re.IGNORECASE)):
        client.chat_via_template([{"role": "user", "content": "hi"}])
