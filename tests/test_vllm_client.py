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
    build_offline_chat_kwargs,
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


def test_build_chat_template_kwargs_false_and_true() -> None:
    """#94 で None (旧 mode=auto) は廃止された。bool のみ受け付ける。"""
    assert build_chat_template_kwargs(False) == {"enable_thinking": False}
    assert build_chat_template_kwargs(True) == {"enable_thinking": True}


def test_build_offline_chat_kwargs_omits_tool_choice() -> None:
    """vLLM offline ``LLM.chat()`` は tool_choice を受け付けないので chat_kwargs に含めない。

    回帰テスト (#109): tool_choice を ``LLM.chat()`` に渡すと
    ``TypeError: got an unexpected keyword argument 'tool_choice'`` となる。
    """
    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "", "parameters": {}},
        }
    ]
    kwargs = build_offline_chat_kwargs(
        enable_thinking=True,
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "search"}},
    )
    assert "tool_choice" not in kwargs
    assert kwargs["tools"] == tools
    assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}
    assert kwargs["use_tqdm"] is False


def test_build_offline_chat_kwargs_string_tool_choice_also_omitted() -> None:
    """文字列形式 (``"required"`` / ``"auto"``) でも同様に渡してはいけない。"""
    kwargs = build_offline_chat_kwargs(
        enable_thinking=False,
        tools=None,
        tool_choice="required",
    )
    assert "tool_choice" not in kwargs
    assert "tools" not in kwargs


def test_build_offline_chat_kwargs_no_tool_choice_passes_through() -> None:
    """tool_choice 未指定時の通常パスは従来通り。"""
    tools = [{"type": "function", "function": {"name": "calc", "parameters": {}}}]
    kwargs = build_offline_chat_kwargs(
        enable_thinking=True,
        tools=tools,
        tool_choice=None,
    )
    assert kwargs == {
        "use_tqdm": False,
        "chat_template_kwargs": {"enable_thinking": True},
        "tools": tools,
    }


def test_chat_via_template_does_not_forward_tool_choice_to_llm_chat() -> None:
    """End-to-end 回帰テスト: ``self._llm.chat()`` に tool_choice キーワードを
    含めないことを保証する。実 vLLM の ``LLM.chat`` シグネチャ
    (`vllm/entrypoints/llm.py` L959-973) には ``tool_choice`` が無いため、
    渡すと HTTP 500 を発生させる。
    """
    from types import SimpleNamespace

    class _StrictMockLLM:
        """``tool_choice`` を kwargs で受け取ったら実機と同じ TypeError を投げる。"""

        def __init__(self) -> None:
            self.received_kwargs: dict[str, object] | None = None

        def chat(self, messages, params, **kwargs):  # type: ignore[no-untyped-def]
            if "tool_choice" in kwargs:
                raise TypeError("chat() got an unexpected keyword argument 'tool_choice'")
            self.received_kwargs = kwargs
            completion = SimpleNamespace(text="ok", finish_reason="stop", token_ids=[1])
            return [SimpleNamespace(outputs=[completion], prompt_token_ids=[1, 2])]

        def get_tokenizer(self):  # type: ignore[no-untyped-def]
            class _TK:
                def apply_chat_template(self, **kw):  # type: ignore[no-untyped-def]
                    return [1, 2, 3]

            return _TK()

    cfg = Config()
    client = VllmClient.from_config(cfg.model, cfg.vllm)
    mock = _StrictMockLLM()
    client._llm = mock

    def _fake_sampling_params(**overrides: object) -> object:
        return SimpleNamespace(**overrides)

    client._sampling_params = _fake_sampling_params  # type: ignore[method-assign]

    result = client.chat_via_template(
        [{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {"name": "search", "description": "", "parameters": {}},
            }
        ],
        tool_choice={"type": "function", "function": {"name": "search"}},
    )

    assert result.answer == "ok"
    assert mock.received_kwargs is not None
    assert "tool_choice" not in mock.received_kwargs
    assert mock.received_kwargs.get("tools") is not None
