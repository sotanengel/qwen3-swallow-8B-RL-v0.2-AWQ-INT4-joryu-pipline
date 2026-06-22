"""LLM-RUBRIC シグナル (R-11)。

第一段の統計シグナルを通過したレコードに対してのみ実行する第二段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from joryu.curate.judge_client import RUBRIC_KEYS, JudgeClient

from . import SignalResult


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


__all__ = ["LLMRubricSignal"]
