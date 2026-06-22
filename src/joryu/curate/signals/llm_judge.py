"""LLM シグナル群 (R-11): LLM-RUBRIC / LLM-PAIR / LLM-SELF。

第一段の統計シグナルを通過したレコードに対してのみ実行する第二段。
LLM-PAIR / LLM-SELF は MVP 後追加 (R-11 残)。
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


__all__ = ["LLMPairSignalContext", "LLMRubricSignal", "LLMSelfSignal"]
