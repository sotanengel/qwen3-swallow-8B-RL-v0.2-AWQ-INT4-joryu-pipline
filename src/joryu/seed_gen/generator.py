"""LLM によるプロンプトバッチ生成 (#318)。"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Protocol

from joryu.seed_gen.config import DomainSpec

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"
FORBIDDEN_MODEL_SUBSTRINGS = ("swallow", "qwen3-swallow")

_TEMPERATURES = (0.7, 0.9, 1.1)
_TOP_PS = (0.9, 0.95)
_PERSONAS = ("一般読者", "学生", "専門家", "初心者", "ビジネスパーソン")


@dataclass(frozen=True)
class SamplingParams:
    temperature: float
    top_p: float


class SeedGenerator(Protocol):
    def generate_batch(
        self,
        *,
        domain: DomainSpec,
        n: int,
        sampling: SamplingParams,
    ) -> list[str]: ...


def _rotation_index(counter: int, size: int) -> int:
    return counter % size if size else 0


def build_seed_prompt(domain: DomainSpec, rng: random.Random) -> str:
    template = rng.choice(domain.seed_templates) if domain.seed_templates else "{theme}"
    theme = rng.choice(domain.themes) if domain.themes else domain.key
    persona = rng.choice(_PERSONAS)
    return template.replace("{theme}", theme).replace("{persona}", persona)


def build_user_message(domain: DomainSpec, n: int, seed_hint: str) -> str:
    return (
        f"カテゴリ「{domain.key}」に沿った日本語の指示プロンプトを {n} 件作成してください。"
        f"参考テーマ: {seed_hint}\n"
        "出力は JSON 配列のみ（説明文不要）。各要素は文字列。"
    )


def parse_prompt_array(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # JSON 配列を抽出
    match = re.search(r"\[[\s\S]*\]", text)
    payload = match.group(0) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("seed_gen: JSON parse failed: %s", text[:200])
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


class FakeSeedGenerator:
    """CI / テスト用決定的ジェネレータ。"""

    def __init__(self, *, start: int = 0) -> None:
        self._counter = start
        self._sampling_counter = 0

    def generate_batch(
        self,
        *,
        domain: DomainSpec,
        n: int,
        sampling: SamplingParams,
    ) -> list[str]:
        del sampling
        prompts: list[str] = []
        for _ in range(n):
            self._counter += 1
            prompts.append(f"[fake:{domain.key}:{self._counter}] テスト用プロンプトです。")
        return prompts

    def next_sampling(self) -> SamplingParams:
        t = _TEMPERATURES[_rotation_index(self._sampling_counter, len(_TEMPERATURES))]
        p = _TOP_PS[_rotation_index(self._sampling_counter, len(_TOP_PS))]
        self._sampling_counter += 1
        return SamplingParams(temperature=t, top_p=p)


class OpenAICompatibleSeedGenerator:
    """OpenAI 互換 HTTP API 経由の生成 (vLLM serve 等)。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        rng: random.Random | None = None,
    ) -> None:
        if any(s in model.lower() for s in FORBIDDEN_MODEL_SUBSTRINGS):
            raise ValueError(f"forbidden seed_gen model: {model}")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._rng = rng or random.Random(42)
        self._sampling_counter = 0

    def next_sampling(self) -> SamplingParams:
        t = _TEMPERATURES[_rotation_index(self._sampling_counter, len(_TEMPERATURES))]
        p = _TOP_PS[_rotation_index(self._sampling_counter, len(_TOP_PS))]
        self._sampling_counter += 1
        return SamplingParams(temperature=t, top_p=p)

    def generate_batch(
        self,
        *,
        domain: DomainSpec,
        n: int,
        sampling: SamplingParams,
    ) -> list[str]:
        import httpx

        seed_hint = build_seed_prompt(domain, self._rng)
        user_msg = build_user_message(domain, n, seed_hint)
        url = f"{self._base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": user_msg}],
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "max_tokens": 2048,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("seed_gen: LLM request failed: %s", exc)
            return []
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.warning("seed_gen: unexpected LLM response shape")
            return []
        return parse_prompt_array(str(content))


__all__ = [
    "DEFAULT_MODEL",
    "FakeSeedGenerator",
    "OpenAICompatibleSeedGenerator",
    "SamplingParams",
    "SeedGenerator",
    "build_seed_prompt",
    "build_user_message",
    "parse_prompt_array",
]
