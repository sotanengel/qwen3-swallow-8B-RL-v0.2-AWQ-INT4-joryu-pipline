"""LLM judge クライアント抽象 (R-11)。

`JudgeClient` プロトコルに準拠した実装を切り替え可能にし、CI では `FakeJudgeClient`
を使って GPU 無しで全経路をテストできるようにする。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from joryu.vllm_client import SupportsChat

logger = logging.getLogger(__name__)

RUBRIC_KEYS: tuple[str, ...] = (
    "accuracy",
    "completeness",
    "fluency",
    "instruction_following",
    "safety",
)


class JudgeClient(Protocol):
    """rubric scoring を担う judge クライアント。"""

    def score_rubric(self, prompt: str, answer: str) -> dict[str, int]: ...


class FakeJudgeClient:
    """テスト/CI 用 fake。固定スコアまたは callable をプロンプトごとに返す。"""

    def __init__(
        self,
        scores: dict[str, int] | None = None,
        *,
        scorer: Callable[[str, str], dict[str, int]] | None = None,
    ) -> None:
        self._scores = scores or {k: 4 for k in RUBRIC_KEYS}
        self._scorer = scorer
        self.calls: list[dict[str, str]] = []

    def score_rubric(self, prompt: str, answer: str) -> dict[str, int]:
        self.calls.append({"prompt": prompt, "answer": answer})
        if self._scorer is not None:
            return self._scorer(prompt, answer)
        return dict(self._scores)


class VllmJudgeClient:
    """既存 VllmClient を judge として使うアダプタ。`SupportsChat` 互換実装を保持。"""

    def __init__(
        self,
        chat: SupportsChat,
        *,
        rubric_prompt: str,
        judge_mode: str = "nothinking",
        max_tokens: int = 128,
        temperature: float = 0.0,
    ) -> None:
        self._chat = chat
        self._rubric_prompt = rubric_prompt
        self._enable_thinking = judge_mode == "thinking"
        self._max_tokens = max_tokens
        self._temperature = temperature

    def score_rubric(self, prompt: str, answer: str) -> dict[str, int]:
        system_msg = self._rubric_prompt
        user_msg = (
            "以下のプロンプトと回答を rubric に従って評価し、JSON のみを返してください。\n\n"
            f"## プロンプト\n{prompt}\n\n## 回答\n{answer}\n"
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
        try:
            _thinking, body = self._chat.chat_via_template(
                messages,
                enable_thinking=self._enable_thinking,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[curate.judge] chat failed: %s", exc)
            return _default_neutral_scores()
        return parse_rubric_response(body)


def _default_neutral_scores() -> dict[str, int]:
    return {k: 3 for k in RUBRIC_KEYS}


def parse_rubric_response(text: str) -> dict[str, int]:
    """LLM レスポンスから rubric JSON を頑健に抽出。

    - ```json コードフェンスを剥がす
    - 最初の `{...}` ブロックを正規表現で拾う
    - パース失敗時は neutral (3,3,3,3,3) を返す
    """
    import json
    import re

    if not text:
        return _default_neutral_scores()
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    match = re.search(r"\{[^{}]*\}", candidate, re.DOTALL)
    if not match:
        return _default_neutral_scores()
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _default_neutral_scores()
    if not isinstance(parsed, dict):
        return _default_neutral_scores()
    out: dict[str, int] = {}
    for k in RUBRIC_KEYS:
        v = parsed.get(k, 3)
        try:
            iv = int(round(float(v)))
        except (TypeError, ValueError):
            iv = 3
        out[k] = max(1, min(5, iv))
    return out


DEFAULT_RUBRIC_PROMPT = (
    "あなたは日本語 SFT データの品質評価者です。与えられたプロンプトに対する回答を、"
    "以下の 5 観点でそれぞれ 1〜5 の整数で評価し、JSON のみを返してください。\n"
    "\n"
    "観点:\n"
    "- accuracy: 事実関係 / 正確性 (5=完全に正しい, 1=明確に誤り)\n"
    "- completeness: 設問に対するカバレッジ (5=十分, 1=主要な要素が抜けている)\n"
    "- fluency: 日本語としての自然さ (5=自然, 1=破綻)\n"
    "- instruction_following: プロンプトの指示への追従 (5=完全に従っている, 1=無視)\n"
    "- safety: 安全性 / 有害性回避 (5=安全, 1=有害)\n"
    "\n"
    "出力フォーマット (必ず JSON のみ、解説不要):\n"
    '{"accuracy": 4, "completeness": 4, "fluency": 5, '
    '"instruction_following": 4, "safety": 5}\n'
)


def get_default_rubric_prompt() -> str:
    return DEFAULT_RUBRIC_PROMPT


__all__ = [
    "DEFAULT_RUBRIC_PROMPT",
    "FakeJudgeClient",
    "JudgeClient",
    "RUBRIC_KEYS",
    "VllmJudgeClient",
    "get_default_rubric_prompt",
    "parse_rubric_response",
]
