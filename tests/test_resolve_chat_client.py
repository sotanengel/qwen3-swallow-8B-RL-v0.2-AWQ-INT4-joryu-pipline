"""resolve_chat_client(): backend 切替のユニットテスト。"""

from __future__ import annotations

import pytest

from joryu.config import Config, ModelConfig, VllmConfig
from joryu.vllm_client import (
    DEFAULT_LOCAL_JORYU_URL,
    DEFAULT_LOCAL_VLLM_URL,
    VllmClient,
    VllmHttpClient,
    resolve_chat_client,
    resolve_stream_chat_client,
)
from joryu.vllm_serve_client import VllmServeClient
from joryu.vllm_stream_client import VllmServeStreamClient


def test_resolve_vllm_serve_backend_returns_serve_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JORYU_VLLM_URL", raising=False)
    cfg = VllmConfig(backend="vllm-serve", serve_url="", model_path="org/my-model")
    client = resolve_chat_client(ModelConfig(name="short-name"), cfg)
    assert isinstance(client, VllmServeClient)
    assert client._base_url == DEFAULT_LOCAL_VLLM_URL.rstrip("/").removesuffix("/v1")
    assert client._model == "org/my-model"


def test_resolve_vllm_serve_backend_uses_env_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://custom:8100/v1")
    cfg = VllmConfig(backend="vllm-serve")
    client = resolve_chat_client(ModelConfig(), cfg)
    assert isinstance(client, VllmServeClient)
    assert client._base_url == "http://custom:8100"


def test_resolve_joryu_llm_serve_backend_returns_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JORYU_VLLM_URL", raising=False)
    cfg = VllmConfig(backend="joryu-llm-serve", serve_url="")
    client = resolve_chat_client(ModelConfig(), cfg)
    assert isinstance(client, VllmHttpClient)
    assert client._base_url == DEFAULT_LOCAL_JORYU_URL


def test_resolve_joryu_llm_serve_backend_uses_env_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://joryu:8100")
    cfg = VllmConfig(backend="joryu-llm-serve")
    client = resolve_chat_client(ModelConfig(), cfg)
    assert isinstance(client, VllmHttpClient)
    assert client._base_url == "http://joryu:8100"


def test_resolve_inproc_backend_ignores_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JORYU_VLLM_URL", "http://localhost:8100")
    cfg = VllmConfig(backend="inproc")
    client = resolve_chat_client(ModelConfig(), cfg)
    assert isinstance(client, VllmClient)


def test_default_backend_is_vllm_serve() -> None:
    assert VllmConfig().backend == "vllm-serve"


def test_fingerprint_unchanged_when_backend_changes() -> None:
    base = Config()
    alt = Config()
    alt.vllm.backend = "joryu-llm-serve"
    assert base.fingerprint() == alt.fingerprint()


def test_resolve_stream_client_vllm_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JORYU_VLLM_URL", raising=False)
    cfg = VllmConfig(backend="vllm-serve", model_path="org/model")
    client = resolve_stream_chat_client(ModelConfig(), cfg)
    assert isinstance(client, VllmServeStreamClient)
    assert client._base_url == DEFAULT_LOCAL_VLLM_URL.rstrip("/").removesuffix("/v1")
    assert client._model == "org/model"


def test_resolve_stream_client_non_vllm_serve_returns_none() -> None:
    assert resolve_stream_chat_client(ModelConfig(), VllmConfig(backend="inproc")) is None
    assert resolve_stream_chat_client(ModelConfig(), VllmConfig(backend="joryu-llm-serve")) is None
