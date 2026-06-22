"""best-of-N 選択 (R-12)。

同一 `(prompt, mode)` グルーピングで生成された複数バリアントから 1 件だけを採用し、
残りは `rejected_by="best_of_n"` で棄却する。直積スイープ (style × temperature × top_p)
の冗長性削減が目的。

戦略:
- `off`: 何もしない (MVP 互換)
- `rubric_max`: LLM-RUBRIC スコア最大 (LLM-RUBRIC が無ければ stat_score 最大)
- `pair_tournament`: LLM-PAIR で総当り → winrate 最大
- `auto`: judge が LLM-PAIR を持っていれば pair_tournament、無ければ rubric_max

タイブレーク: `record_hash` の辞書順最小 (決定的)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from joryu.curate.judge_client import JudgeClient
from joryu.curate.scoring import CompositeScore
from joryu.curate.signals.llm_judge import LLMPairSignalContext

logger = logging.getLogger(__name__)

BEST_OF_N_REJECTED = "BEST-OF-N"

Strategy = Literal["off", "rubric_max", "pair_tournament", "auto"]


@dataclass
class BestOfNResult:
    """各レコードの best-of-N 判定結果。"""

    group_key: tuple[str, str]
    is_winner: bool
    group_size: int
    winrate: float | None = None


def _group_key(record: dict[str, Any]) -> tuple[str, str]:
    return (str(record.get("prompt") or ""), str(record.get("mode") or ""))


def _rubric_score(composite: CompositeScore) -> float:
    """LLM-RUBRIC があればそれを優先、無ければ stat_score。"""
    if "LLM-RUBRIC" in composite.signal_scores:
        return float(composite.signal_scores["LLM-RUBRIC"])
    return float(composite.stat_score)


def parse_strategy(value: str | None) -> Strategy:
    """CLI `--best-of-n` 文字列を Strategy にパース。

    `off` / `auto` / `rubric_max` / `pair_tournament` / `n=<int>` を受け付ける。
    `n=<int>` は MVP では `auto` と同義 (グループサイズ N のうち 1 件選ぶ意味は同じ)。
    """
    if value is None or value == "" or value == "off":
        return "off"
    v = value.strip().lower()
    if v in ("auto", "rubric_max", "pair_tournament"):
        return v  # type: ignore[return-value]
    if v.startswith("n="):
        return "auto"
    raise ValueError(f"unsupported --best-of-n value: {value!r}")


def apply_best_of_n(
    records: list[dict[str, Any]],
    composites: list[CompositeScore],
    record_hashes: list[str],
    *,
    strategy: Strategy = "off",
    judge: JudgeClient | None = None,
) -> list[BestOfNResult]:
    """同一 `(prompt, mode)` グループで 1 件だけ winner を残し、他は hard_reject する。

    in-place で `composites[i].hard_rejected_by` に `BEST_OF_N_REJECTED` を追記。
    判定は **ハード棄却済みでないレコードのみ** が対象 (既に棄却なら winner 候補にも入れない)。
    """
    if strategy == "off":
        return [
            BestOfNResult((str(r.get("prompt") or ""), str(r.get("mode") or "")), True, 1)
            for r in records
        ]

    if not (len(records) == len(composites) == len(record_hashes)):
        raise ValueError("入力リスト長が一致しません")

    # グループ化 (ハード棄却済みは除外)
    groups: dict[tuple[str, str], list[int]] = {}
    for i, (rec, comp) in enumerate(zip(records, composites, strict=True)):
        if comp.hard_rejected:
            continue
        groups.setdefault(_group_key(rec), []).append(i)

    results: list[BestOfNResult] = [
        BestOfNResult(_group_key(records[i]), True, 1) for i in range(len(records))
    ]

    resolved_strategy = strategy
    if strategy == "auto":
        resolved_strategy = "pair_tournament" if _judge_supports_pair(judge) else "rubric_max"

    pair_ctx: LLMPairSignalContext | None = None
    if resolved_strategy == "pair_tournament":
        if judge is None or not _judge_supports_pair(judge):
            logger.warning(
                "[curate.best_of_n] pair_tournament 要求だが judge が pair 未対応。"
                "rubric_max に降格"
            )
            resolved_strategy = "rubric_max"
        else:
            pair_ctx = LLMPairSignalContext(judge=judge)

    for key, idxs in groups.items():
        n = len(idxs)
        if n <= 1:
            for i in idxs:
                results[i] = BestOfNResult(key, True, n)
            continue

        if resolved_strategy == "pair_tournament" and pair_ctx is not None:
            winrate = pair_ctx.evaluate_group(records, idxs)
            # winrate 最大、タイなら record_hash 辞書順最小
            winner = sorted(idxs, key=lambda i: (-winrate[i], record_hashes[i]))[0]
            for i in idxs:
                w = i == winner
                results[i] = BestOfNResult(key, w, n, winrate.get(i))
                # LLM-PAIR の winrate を signal_scores にも記録 (キャッシュ再利用用)
                composites[i].signal_scores["LLM-PAIR"] = winrate.get(i, 0.0)
                composites[i].signal_versions.setdefault("LLM-PAIR", pair_ctx.version)
                if not w:
                    composites[i].hard_rejected_by.append(BEST_OF_N_REJECTED)
        else:  # rubric_max
            winner = sorted(idxs, key=lambda i: (-_rubric_score(composites[i]), record_hashes[i]))[
                0
            ]
            for i in idxs:
                w = i == winner
                results[i] = BestOfNResult(key, w, n)
                if not w:
                    composites[i].hard_rejected_by.append(BEST_OF_N_REJECTED)

    return results


def _judge_supports_pair(judge: JudgeClient | None) -> bool:
    return judge is not None and hasattr(judge, "compare_pair")


__all__ = [
    "BEST_OF_N_REJECTED",
    "BestOfNResult",
    "Strategy",
    "apply_best_of_n",
    "parse_strategy",
]
