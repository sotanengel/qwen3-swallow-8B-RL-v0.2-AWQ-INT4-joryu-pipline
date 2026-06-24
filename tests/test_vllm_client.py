"""vllm_client.py: thin wrapper のメッセージ整形・thinking 解析・SamplingParams 構築。

実 vLLM はロードせず、内部メソッドのユニットテストと FakeVllmClient 仕様の確認のみ。
"""

from __future__ import annotations

import re

import pytest

from joryu.config import Config
from joryu.vllm_client import (
    ChatResult,
    SupportsChat,
    VllmClient,
    build_chat_template_kwargs,
    compute_effective_max_tokens,
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


def test_vllm_client_from_config_propagates_memory_savers() -> None:
    """KV FP8 / prefix cache / max_num_seqs / swap が VllmClient に渡る。"""
    cfg = Config()
    cfg.vllm.kv_cache_dtype = "fp8"
    cfg.vllm.enable_prefix_caching = True
    cfg.vllm.max_num_seqs = 1
    cfg.vllm.swap_space_gib = 4
    client = VllmClient.from_config(cfg.model, cfg.vllm)
    assert client._kv_cache_dtype == "fp8"
    assert client._enable_prefix_caching is True
    assert client._max_num_seqs == 1
    assert client._swap_space_gib == 4


def test_compute_effective_max_tokens_clamps_to_context() -> None:
    assert (
        compute_effective_max_tokens(
            requested_max_tokens=1024,
            max_model_len=512,
            prompt_tokens=200,
        )
        == 280
    )


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


def test_supports_chat_protocol_signature() -> None:
    class _Fake:
        def chat_via_template(
            self,
            messages: list[dict[str, str]],
            *,
            enable_thinking: bool | None = True,
            **sampling_overrides: object,
        ) -> ChatResult:
            return ChatResult(
                thinking=None,
                answer="ok",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )

    fake: SupportsChat = _Fake()
    result = fake.chat_via_template([{"role": "user", "content": "hi"}])
    assert result.thinking is None
    assert result.answer == "ok"


def test_build_chat_template_kwargs_auto_omits_key() -> None:
    assert build_chat_template_kwargs(None) == {}
    assert "enable_thinking" not in build_chat_template_kwargs(None)


def test_build_chat_template_kwargs_false_and_true() -> None:
    assert build_chat_template_kwargs(False) == {"enable_thinking": False}
    assert build_chat_template_kwargs(True) == {"enable_thinking": True}
