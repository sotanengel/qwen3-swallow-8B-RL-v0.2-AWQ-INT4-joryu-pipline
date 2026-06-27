"""シグナル合成スコア + 採否判定 (R-13)。

`score = w_stat * f_stat(統計シグナル) + w_llm * f_llm(LLMシグナル)`

ハード棄却ルール (LEN, TRUNC, THINK-TAG, LANG-JA, REPEAT, DUP-GLOB) を全て
通過し、かつ合成スコアが threshold/top_k/keep_rate のいずれかを満たした
レコードのみを採用する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from joryu.curate.signals import SignalResult

ScreeningLabel = Literal["OK", "REVIEW", "NG"]


@dataclass
class CompositeScore:
    """1 レコードの合成スコア + 採否判定の中間表現。"""

    stat_score: float
    llm_score: float | None
    final_score: float
    hard_rejected_by: list[str] = field(default_factory=list)
    signal_versions: dict[str, str] = field(default_factory=dict)
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_raw: dict[str, object] = field(default_factory=dict)

    @property
    def hard_rejected(self) -> bool:
        return bool(self.hard_rejected_by)


def f_stat(signals: list[SignalResult]) -> float:
    """統計シグナルを [0,1] の加重 (等重み) 平均。

    DUP-GLOB / TRUNC など 0/1 系も同じスケールで混ぜる。要件で別 tuning が
    入った時点で個別重みを CurateConfig に外出しする。
    """
    if not signals:
        return 0.0
    return sum(s.score for s in signals) / len(signals)


def f_llm(signals: list[SignalResult]) -> float | None:
    """LLM 系シグナル。今は LLM-RUBRIC のみなので直接平均。"""
    if not signals:
        return None
    return sum(s.score for s in signals) / len(signals)


def compose_score(
    stat_score: float,
    llm_score: float | None,
    *,
    w_stat: float,
    w_llm: float,
) -> float:
    """合成スコアを返す。LLM が無ければ stat 100% に正規化。"""
    if llm_score is None:
        return stat_score
    total_w = w_stat + w_llm
    if total_w <= 0:
        return 0.0
    return (w_stat * stat_score + w_llm * llm_score) / total_w


def build_composite(
    *,
    stat_results: list[SignalResult],
    llm_results: list[SignalResult],
    w_stat: float,
    w_llm: float,
) -> CompositeScore:
    """シグナル結果をまとめて CompositeScore を作る。"""
    hard: list[str] = [s.code for s in stat_results if s.hard_reject]
    hard.extend(s.code for s in llm_results if s.hard_reject)
    stat_s = f_stat(stat_results)
    llm_s = f_llm(llm_results) if llm_results else None
    final = compose_score(stat_s, llm_s, w_stat=w_stat, w_llm=w_llm)
    versions: dict[str, str] = {}
    scores: dict[str, float] = {}
    raw: dict[str, object] = {}
    for s in (*stat_results, *llm_results):
        versions[s.code] = s.version
        scores[s.code] = s.score
        raw[s.code] = s.raw
    return CompositeScore(
        stat_score=stat_s,
        llm_score=llm_s,
        final_score=final,
        hard_rejected_by=hard,
        signal_versions=versions,
        signal_scores=scores,
        signal_raw=raw,
    )


@dataclass
class SelectionResult:
    """採否判定の最終結果。"""

    accepted: bool
    final_score: float
    rejected_by: list[str]


def select_by_threshold(
    composites: list[CompositeScore],
    *,
    threshold: float,
    top_k: int | None = None,
    keep_rate: float | None = None,
) -> list[SelectionResult]:
    """3 つの選抜方式 (threshold / top_k / keep_rate) を相互排他で適用。

    優先順位: keep_rate > top_k > threshold。
    keep_rate は [0,1] の小数として解釈 (要件 7 章では百分率記載だが、
    内部は 0-1 で統一する。CLI 側で変換)。
    """
    # ハード棄却済みは無条件で reject。
    survivors: list[tuple[int, CompositeScore]] = [
        (i, c) for i, c in enumerate(composites) if not c.hard_rejected
    ]
    n_survivors = len(survivors)
    accept_set: set[int] = set()
    if n_survivors == 0:
        pass
    elif keep_rate is not None:
        k = max(0, min(n_survivors, int(round(keep_rate * n_survivors))))
        ranked = sorted(survivors, key=lambda t: t[1].final_score, reverse=True)[:k]
        accept_set = {idx for idx, _ in ranked}
    elif top_k is not None:
        k = max(0, min(n_survivors, top_k))
        ranked = sorted(survivors, key=lambda t: t[1].final_score, reverse=True)[:k]
        accept_set = {idx for idx, _ in ranked}
    else:
        accept_set = {idx for idx, c in survivors if c.final_score >= threshold}

    out: list[SelectionResult] = []
    for i, c in enumerate(composites):
        if c.hard_rejected:
            out.append(SelectionResult(False, c.final_score, list(c.hard_rejected_by)))
        elif i in accept_set:
            out.append(SelectionResult(True, c.final_score, []))
        else:
            out.append(SelectionResult(False, c.final_score, ["BELOW_THRESHOLD"]))
    return out


def screening_label(
    final_score: float,
    *,
    ok_min: float,
    review_min: float,
) -> ScreeningLabel:
    """3 段階健全性ラベル (要件 §6.2)。"""
    if final_score >= ok_min:
        return "OK"
    if final_score >= review_min:
        return "REVIEW"
    return "NG"


def apply_max_review_rate(
    labels: list[ScreeningLabel],
    scores: list[float],
    *,
    max_rate: float,
) -> list[ScreeningLabel]:
    """REVIEW 件数が max_rate を超える場合、低スコア REVIEW を NG に降格。"""
    if not labels:
        return labels
    n = len(labels)
    max_review = int(max_rate * n)
    review_idxs = [i for i, lbl in enumerate(labels) if lbl == "REVIEW"]
    if len(review_idxs) <= max_review:
        return labels
    excess = len(review_idxs) - max_review
    # スコアが低い REVIEW から NG に降格
    sorted_review = sorted(review_idxs, key=lambda i: scores[i])
    demote = set(sorted_review[:excess])
    out: list[ScreeningLabel] = list(labels)
    for i in demote:
        out[i] = "NG"
    return out


def label_screening_batch(
    composites: list[CompositeScore],
    *,
    ok_min: float,
    review_min: float,
    max_review_rate: float,
) -> list[ScreeningLabel]:
    """CompositeScore 群から screening ラベル列を生成。"""
    labels: list[ScreeningLabel] = []
    scores: list[float] = []
    for comp in composites:
        if comp.hard_rejected:
            labels.append("NG")
        else:
            labels.append(screening_label(comp.final_score, ok_min=ok_min, review_min=review_min))
        scores.append(comp.final_score)
    return apply_max_review_rate(labels, scores, max_rate=max_review_rate)


__all__ = [
    "CompositeScore",
    "ScreeningLabel",
    "SelectionResult",
    "apply_max_review_rate",
    "build_composite",
    "compose_score",
    "f_llm",
    "f_stat",
    "label_screening_batch",
    "screening_label",
    "select_by_threshold",
]
