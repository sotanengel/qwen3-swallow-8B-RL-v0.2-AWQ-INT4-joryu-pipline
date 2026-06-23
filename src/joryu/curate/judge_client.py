"""LLM judge クライアント抽象 (R-11)。

`JudgeClient` プロトコルに準拠した実装を切り替え可能にし、CI では `FakeJudgeClient`
を使って GPU 無しで全経路をテストできるようにする。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any, Literal, Protocol

from joryu.vllm_client import SupportsChat

logger = logging.getLogger(__name__)

RUBRIC_KEYS: tuple[str, ...] = (
    "accuracy",
    "completeness",
    "fluency",
    "instruction_following",
    "safety",
)


PairWinner = Literal["a", "b", "tie"]


class JudgeClient(Protocol):
    """rubric scoring + pairwise 比較 + self-consistency を担う judge クライアント。"""

    def score_rubric(self, prompt: str, answer: str) -> dict[str, int]: ...

    def compare_pair(self, prompt: str, answer_a: str, answer_b: str) -> PairWinner: ...

    def score_self_consistency(self, prompt: str, thinking: str, answer: str) -> float: ...


class FakeJudgeClient:
    """テスト/CI 用 fake。

    - `scores` / `scorer`: rubric の固定スコア or callable
    - `pair_winner` / `pair_scorer`: pairwise 比較の戻り値固定 or callable
    - `self_score` / `self_scorer`: self-consistency の戻り値固定 or callable
    """

    def __init__(
        self,
        scores: dict[str, int] | None = None,
        *,
        scorer: Callable[[str, str], dict[str, int]] | None = None,
        pair_winner: PairWinner = "tie",
        pair_scorer: Callable[[str, str, str], PairWinner] | None = None,
        self_score: float = 1.0,
        self_scorer: Callable[[str, str, str], float] | None = None,
    ) -> None:
        self._scores = scores or {k: 4 for k in RUBRIC_KEYS}
        self._scorer = scorer
        self._pair_winner = pair_winner
        self._pair_scorer = pair_scorer
        self._self_score = self_score
        self._self_scorer = self_scorer
        self.calls: list[dict[str, str]] = []
        self.pair_calls: list[dict[str, str]] = []
        self.self_calls: list[dict[str, str]] = []

    def score_rubric(self, prompt: str, answer: str) -> dict[str, int]:
        self.calls.append({"prompt": prompt, "answer": answer})
        if self._scorer is not None:
            return self._scorer(prompt, answer)
        return dict(self._scores)

    def compare_pair(self, prompt: str, answer_a: str, answer_b: str) -> PairWinner:
        self.pair_calls.append({"prompt": prompt, "a": answer_a, "b": answer_b})
        if self._pair_scorer is not None:
            return self._pair_scorer(prompt, answer_a, answer_b)
        return self._pair_winner

    def score_self_consistency(self, prompt: str, thinking: str, answer: str) -> float:
        self.self_calls.append({"prompt": prompt, "thinking": thinking, "answer": answer})
        if self._self_scorer is not None:
            return self._self_scorer(prompt, thinking, answer)
        return self._self_score


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
            result = self._chat.chat_via_template(
                messages,
                enable_thinking=self._enable_thinking,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[curate.judge] chat failed: %s", exc)
            return _default_neutral_scores()
        return parse_rubric_response(result.answer)

    def compare_pair(self, prompt: str, answer_a: str, answer_b: str) -> PairWinner:
        messages = [
            {"role": "system", "content": DEFAULT_PAIR_PROMPT},
            {
                "role": "user",
                "content": (
                    "以下のプロンプトに対する 2 つの回答 A / B を比較し、"
                    'JSON `{"winner": "a"|"b"|"tie"}` のみを返してください。\n\n'
                    f"## プロンプト\n{prompt}\n\n## 回答 A\n{answer_a}\n\n## 回答 B\n{answer_b}\n"
                ),
            },
        ]
        try:
            result = self._chat.chat_via_template(
                messages,
                enable_thinking=self._enable_thinking,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[curate.judge.pair] chat failed: %s", exc)
            return "tie"
        return parse_pair_response(result.answer)

    def score_self_consistency(self, prompt: str, thinking: str, answer: str) -> float:
        # thinking モードで自己評価。bias を抑えるため thinking モード固定。
        messages = [
            {"role": "system", "content": DEFAULT_SELF_PROMPT},
            {
                "role": "user",
                "content": (
                    "以下の thinking と answer の整合性を 0.0〜1.0 で評価し、"
                    'JSON `{"score": <0-1 の float>}` のみを返してください。\n\n'
                    f"## プロンプト\n{prompt}\n\n## thinking\n{thinking}\n\n## answer\n{answer}\n"
                ),
            },
        ]
        try:
            result = self._chat.chat_via_template(
                messages,
                enable_thinking=True,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[curate.judge.self] chat failed: %s", exc)
            return 0.5
        return parse_self_response(result.answer)


def _default_neutral_scores() -> dict[str, int]:
    return {k: 3 for k in RUBRIC_KEYS}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """LLM レスポンスから最初の JSON object を抽出する。"""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    match = re.search(r"\{[^{}]*\}", candidate, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_rubric_response(text: str) -> dict[str, int]:
    """LLM レスポンスから rubric JSON を頑健に抽出。

    - ```json コードフェンスを剥がす
    - 最初の `{...}` ブロックを正規表現で拾う
    - パース失敗時は neutral (3,3,3,3,3) を返す
    """
    parsed = _extract_json_object(text)
    if parsed is None:
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

DEFAULT_PAIR_PROMPT = (
    "あなたは日本語 SFT データの品質審判です。同一プロンプトに対する 2 つの回答 A / B を比較し、"
    "どちらが優れているか、または同等かを判定してください。バイアスを避けるため、長さの差だけで"
    "判定せず、正確性 / 流暢性 / 指示追従の総合で判断してください。\n"
    "\n"
    "出力フォーマット (必ず JSON のみ、解説不要):\n"
    '{"winner": "a"} もしくは {"winner": "b"} もしくは {"winner": "tie"}\n'
)

DEFAULT_SELF_PROMPT = (
    "あなたは日本語 SFT データの整合性審判です。thinking (思考プロセス) と answer (最終回答) が"
    "論理的に整合しているか、矛盾なく結論に至っているかを 0.0〜1.0 のスコアで評価してください。\n"
    "1.0 = 完全に整合 / 0.5 = 一部不整合 / 0.0 = 思考と回答が矛盾している。\n"
    "\n"
    "出力フォーマット (必ず JSON のみ、解説不要):\n"
    '{"score": 0.85}\n'
)


def get_default_rubric_prompt() -> str:
    return DEFAULT_RUBRIC_PROMPT


def parse_pair_response(text: str) -> PairWinner:
    """LLM レスポンスから `{"winner": ...}` を頑健に抽出。fallback = "tie"."""
    parsed = _extract_json_object(text)
    if parsed is None:
        return "tie"
    winner = parsed.get("winner")
    if isinstance(winner, str):
        w = winner.strip().lower()
        if w in ("a", "b", "tie"):
            return w  # type: ignore[return-value]
    return "tie"


def parse_self_response(text: str) -> float:
    """LLM レスポンスから `{"score": float}` を頑健に抽出。fallback = 0.5."""
    parsed = _extract_json_object(text)
    if parsed is None:
        return 0.5
    s = parsed.get("score")
    try:
        f = float(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


__all__ = [
    "DEFAULT_PAIR_PROMPT",
    "DEFAULT_RUBRIC_PROMPT",
    "DEFAULT_SELF_PROMPT",
    "FakeJudgeClient",
    "JudgeClient",
    "PairWinner",
    "RUBRIC_KEYS",
    "VllmJudgeClient",
    "get_default_rubric_prompt",
    "parse_pair_response",
    "parse_rubric_response",
    "parse_self_response",
]
