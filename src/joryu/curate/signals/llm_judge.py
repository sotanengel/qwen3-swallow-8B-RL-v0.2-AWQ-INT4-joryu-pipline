"""LLM シグナル群 (R-11): LLM-RUBRIC / LLM-PAIR / LLM-SELF。

第一段の統計シグナルを通過したレコードに対してのみ実行する第二段。
LLM-PAIR / LLM-SELF は MVP 後追加 (R-11 残)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from joryu.curate.judge_client import (
    HEALTH_RUBRIC_KEYS,
    PROMPT_HEALTH_RUBRIC_KEYS,
    RUBRIC_KEYS,
    JudgeClient,
)

from . import SignalResult


def truncate_for_health(text: str, *, max_each: int = 500) -> str:
    """think 長文を冒頭/末尾に truncate (要件 §9)。"""
    if len(text) <= max_each * 2:
        return text
    return f"{text[:max_each]}\n...\n{text[-max_each:]}"


def build_health_response_text(record: dict[str, Any]) -> str:
    tt = record.get("thinking_trace") or record.get("reasoning") or ""
    ans = record.get("answer") or ""
    if tt:
        return f"{truncate_for_health(tt)}\n{ans}"
    return ans


@dataclass
class LLMRubricSignal:
    """5 観点 (accuracy/completeness/fluency/instruction_following/safety) の平均/5。"""

    code: str = "LLM-RUBRIC"
    version: str = "v1"
    judge: JudgeClient = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        prompt = record.get("prompt") or ""
        answer = record.get("answer") or ""
        scores = self.judge.score_rubric(prompt, answer)
        valid = [scores.get(k, 3) for k in RUBRIC_KEYS]
        avg = sum(valid) / len(valid) if valid else 3.0
        normalized = avg / 5.0
        return SignalResult(self.code, self.version, normalized, scores, hard_reject=False)


@dataclass
class LlmHealthRubric:
    """健全性 LLM rubric (L-01〜L-05)。学習価値 rubric (LLM-RUBRIC) とは別シグナル。"""

    code: str = "LLM-HEALTH"
    version: str = "health_rubric.ja.v1.0"
    judge: JudgeClient = None  # type: ignore[assignment]
    prompt_template: str = ""

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        prompt = record.get("prompt") or ""
        response = build_health_response_text(record)
        scores = self.judge.score_health_rubric(
            prompt,
            response,
            health_prompt_template=self.prompt_template,
        )
        valid = [scores.get(k, 3) for k in HEALTH_RUBRIC_KEYS]
        avg = sum(valid) / len(valid) if valid else 3.0
        normalized = avg / 5.0
        return SignalResult(self.code, self.version, normalized, scores, hard_reject=False)


@dataclass
class LlmPromptHealthRubric:
    """プロンプトバンク専用 LLM rubric (P-01〜P-05)。応答は評価しない。"""

    code: str = "LLM-PROMPT-HEALTH"
    version: str = "prompt_health_rubric.ja.v1.0"
    judge: JudgeClient = None  # type: ignore[assignment]
    prompt_template: str = ""

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        prompt = record.get("prompt") or ""
        scores = self.judge.score_prompt_health_rubric(
            prompt,
            health_prompt_template=self.prompt_template,
        )
        valid = [scores.get(k, 3) for k in PROMPT_HEALTH_RUBRIC_KEYS]
        avg = sum(valid) / len(valid) if valid else 3.0
        normalized = avg / 5.0
        return SignalResult(self.code, self.version, normalized, scores, hard_reject=False)


@dataclass
class LLMSelfSignal:
    """thinking モードのレコードに対し thinking ↔ answer の整合性を [0,1] でスコア化。

    nothinking モードでは中立 (score=1.0, hard=False) を返し LLM 呼び出しを抑制。
    """

    code: str = "LLM-SELF"
    version: str = "v1"
    judge: JudgeClient = None  # type: ignore[assignment]
    hard_min: float | None = None  # 設定時、これ未満で hard_reject

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if record.get("mode") != "thinking":
            return SignalResult(self.code, self.version, 1.0, None, False)
        thinking = record.get("thinking_trace") or record.get("reasoning") or ""
        answer = record.get("answer") or ""
        if not thinking or not answer:
            return SignalResult(self.code, self.version, 0.5, None, False)
        score = self.judge.score_self_consistency(record.get("prompt") or "", thinking, answer)
        hard = bool(self.hard_min is not None and score < self.hard_min)
        return SignalResult(self.code, self.version, score, score, hard)


@dataclass
class LLMPairSignalContext:
    """LLM-PAIR の評価コンテキスト。同一 `(prompt, mode)` グループの index と勝率を保持。

    `evaluate_group(records, indices)` がグループ全体で pairwise 比較を行い、
    `winrate[i]` を返す。これは best_of_n から再利用する想定 (R-12)。
    """

    judge: JudgeClient
    code: str = "LLM-PAIR"
    version: str = "v1"

    def evaluate_group(
        self,
        records: list[dict[str, Any]],
        indices: list[int],
    ) -> dict[int, float]:
        """グループ内 pairwise winrate を返す。グループ size < 2 なら全員 winrate=1.0。"""
        n = len(indices)
        if n < 2:
            return {i: 1.0 for i in indices}
        wins: dict[int, float] = dict.fromkeys(indices, 0.0)
        matches: dict[int, int] = dict.fromkeys(indices, 0)
        for ai, i in enumerate(indices):
            for j in indices[ai + 1 :]:
                prompt = records[i].get("prompt") or records[j].get("prompt") or ""
                a_text = records[i].get("answer") or ""
                b_text = records[j].get("answer") or ""
                w = self.judge.compare_pair(prompt, a_text, b_text)
                matches[i] += 1
                matches[j] += 1
                if w == "a":
                    wins[i] += 1.0
                elif w == "b":
                    wins[j] += 1.0
                else:  # tie
                    wins[i] += 0.5
                    wins[j] += 0.5
        return {i: (wins[i] / matches[i]) if matches[i] else 0.5 for i in indices}


__all__ = [
    "LLMPairSignalContext",
    "LLMRubricSignal",
    "LLMSelfSignal",
    "LlmHealthRubric",
    "build_health_response_text",
    "truncate_for_health",
]
