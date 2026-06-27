"""統計シグナル (R-10): LLM 呼び出し不要、CPU で 100k/min 以上を狙う第一段フィルタ。

要件 6.1 の各シグナルを 1 クラス = 1 シグナルとして実装する。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

from joryu.config import CurateSignalThresholds
from joryu.curate.minhash_index import GlobalDuplicateIndex
from joryu.curate.style_presets import DEFAULT_STYLE_RULES, StyleRule

from . import Signal, SignalResult
from .health import CtrlChar, EndWell, SyntaxBreak, TemplateLeak
from .quality import FactualHallucination, StyleFormat, ToolLeak, VirtualData
from .tool_use import ActionClaimWithoutCall, ToolPlannedNotCalled

SAMP_OUT_CODE = "SAMP-OUT"
SAMP_OUT_VERSION = "v1"

_KANA_HIRA = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_THINK_OPEN = re.compile(r"<think>")
_THINK_CLOSE = re.compile(r"</think>")


def _normalize_inverse(value: float) -> float:
    """値が大きいほどスコアが下がる [0,1] への単純マッピング。"""
    return max(0.0, min(1.0, 1.0 - value))


# ---------- LEN-A / LEN-T ----------


@dataclass
class LenAnswer:
    """回答文字数。短すぎ / 長すぎ で hard_reject。"""

    code: str = "LEN-A"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        n = len(record.get("answer") or "")
        hard = n < self.th.len_a_min or n > self.th.len_a_max
        ideal = (self.th.len_a_min + self.th.len_a_max) / 2.0
        spread = max(1.0, (self.th.len_a_max - self.th.len_a_min) / 2.0)
        score = max(0.0, 1.0 - abs(n - ideal) / spread)
        return SignalResult(self.code, self.version, score, n, hard)


@dataclass
class LenThinking:
    code: str = "LEN-T"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if record.get("mode") != "thinking":
            return SignalResult(self.code, self.version, 1.0, None, False)
        tt = record.get("thinking_trace") or record.get("reasoning") or ""
        n = len(tt)
        hard = n < self.th.len_t_min or n > self.th.len_t_max
        ideal = (self.th.len_t_min + self.th.len_t_max) / 2.0
        spread = max(1.0, (self.th.len_t_max - self.th.len_t_min) / 2.0)
        score = max(0.0, 1.0 - abs(n - ideal) / spread)
        return SignalResult(self.code, self.version, score, n, hard)


@dataclass
class RatioTA:
    code: str = "RATIO-TA"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if record.get("mode") != "thinking":
            return SignalResult(self.code, self.version, 1.0, None, False)
        ans = len(record.get("answer") or "")
        if ans == 0:
            return SignalResult(self.code, self.version, 0.0, None, True)
        tt = len(record.get("thinking_trace") or record.get("reasoning") or "")
        ratio = tt / ans
        hard = ratio < self.th.ratio_ta_min or ratio > self.th.ratio_ta_max
        score = 1.0 if 0.5 <= ratio <= 3.0 else 0.5
        return SignalResult(self.code, self.version, score, ratio, hard)


# ---------- TRUNC / THINK-TAG ----------


@dataclass
class Truncated:
    code: str = "TRUNC"
    version: str = "v2"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        from joryu.truncation import record_looks_truncated

        fr = record.get("finish_reason")
        if fr == "length":
            truncated = True
        elif fr == "stop":
            truncated = False
        else:
            truncated = record_looks_truncated(record)
        detail = fr if fr is not None else ("heuristic" if truncated else "ok")
        return SignalResult(
            self.code, self.version, 0.0 if truncated else 1.0, detail, hard_reject=truncated
        )


@dataclass
class ThinkTag:
    code: str = "THINK-TAG"
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        if record.get("mode") != "thinking":
            return SignalResult(self.code, self.version, 1.0, None, False)
        text = (record.get("answer") or "") + (record.get("thinking_trace") or "")
        opens = len(_THINK_OPEN.findall(text))
        closes = len(_THINK_CLOSE.findall(text))
        # 同数なら OK (どちらも 0 でも問題なし: thinking_trace に既に展開済み)
        symmetric = opens == closes
        return SignalResult(
            self.code,
            self.version,
            1.0 if symmetric else 0.0,
            {"open": opens, "close": closes},
            hard_reject=not symmetric,
        )


# ---------- LANG-JA ----------


@dataclass
class LangJapanese:
    code: str = "LANG-JA"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = record.get("answer") or ""
        if not text:
            return SignalResult(self.code, self.version, 0.0, 0.0, True)
        meaningful = [c for c in text if not c.isspace() and unicodedata.category(c)[0] != "P"]
        if not meaningful:
            return SignalResult(self.code, self.version, 0.0, 0.0, True)
        ja = sum(1 for c in meaningful if _KANA_HIRA.match(c))
        ratio = ja / len(meaningful)
        hard = ratio < self.th.lang_ja_min
        return SignalResult(self.code, self.version, ratio, ratio, hard)


# ---------- REPEAT-NG (4-gram) / REPEAT-CHAR ----------


@dataclass
class RepeatNGram:
    code: str = "REPEAT-NG"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]
    n: int = 4

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = record.get("answer") or ""
        if len(text) < self.n * 2:
            return SignalResult(self.code, self.version, 1.0, 0.0, False)
        grams = [text[i : i + self.n] for i in range(len(text) - self.n + 1)]
        if not grams:
            return SignalResult(self.code, self.version, 1.0, 0.0, False)
        counts = Counter(grams)
        repeated = sum(c for c in counts.values() if c > 1)
        ratio = repeated / len(grams)
        hard = ratio > self.th.repeat_ng_max
        return SignalResult(self.code, self.version, _normalize_inverse(ratio), ratio, hard)


@dataclass
class RepeatChar:
    code: str = "REPEAT-CHAR"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = record.get("answer") or ""
        if not text:
            return SignalResult(self.code, self.version, 1.0, 0, False)
        max_run = 1
        run = 1
        prev = text[0]
        for ch in text[1:]:
            if ch == prev:
                run += 1
                if run > max_run:
                    max_run = run
            else:
                prev = ch
                run = 1
        hard = max_run > self.th.repeat_char_max
        score = 1.0 if max_run <= 5 else max(0.0, 1.0 - (max_run - 5) / 50.0)
        return SignalResult(self.code, self.version, score, max_run, hard)


# ---------- DUP-GLOB (in-run only for MVP) ----------


class DupGlobal:
    """`answer` のラン跨ぎグローバル重複検出 (R-24 MinHash 永続化対応)。

    既定では in-memory の `GlobalDuplicateIndex` を内部で 1 つ持つ。CLI 側で
    永続化済みの index を `inject_index()` で差し込むことで、過去ラン分も含めた
    重複判定が可能になる。datasketch 未インストール環境では SHA1 完全一致に
    フォールバック (`GlobalDuplicateIndex` 側で吸収)。
    """

    code = "DUP-GLOB"
    version = "v2"  # MinHash 対応で v1 → v2

    def __init__(self, *, index: GlobalDuplicateIndex | None = None) -> None:
        self._index = index or GlobalDuplicateIndex()

    @property
    def index(self) -> GlobalDuplicateIndex:
        return self._index

    def inject_index(self, index: GlobalDuplicateIndex) -> None:
        self._index = index

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = (record.get("answer") or "").strip()
        if not text:
            return SignalResult(self.code, self.version, 0.0, "empty", True)
        rh = (
            record.get("_record_hash")
            or hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()
        )
        is_dup, dup_with = self._index.query_and_insert(str(rh), text)
        if is_dup:
            return SignalResult(self.code, self.version, 0.0, {"dup_with": dup_with}, True)
        return SignalResult(self.code, self.version, 1.0, None, False)


# ---------- STYLE-ADH (per-record) ----------


@dataclass
class StyleAdherence:
    """指定 `style_id` のプリセットに対する文末/キーワード一致率。

    `record["style_id"]` が None またはルール未定義の場合は中立 (score=1.0, hard=False)
    を返す。styles.yaml に declarations のあるプリセットだけ対象になる。
    """

    code: str = "STYLE-ADH"
    version: str = "v1"
    th: CurateSignalThresholds = None  # type: ignore[assignment]
    rules: dict[str, StyleRule] | None = None

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        style_id = record.get("style_id")
        rules = self.rules or DEFAULT_STYLE_RULES
        if not isinstance(style_id, str) or style_id not in rules:
            return SignalResult(self.code, self.version, 1.0, None, False)
        text = record.get("answer") or ""
        if not text:
            return SignalResult(self.code, self.version, 0.0, 0.0, True)
        rule = rules[style_id]
        adh = rule.adherence(text)
        hard = adh < rule.min_adherence
        return SignalResult(self.code, self.version, adh, adh, hard)


# ---------- SAMP-OUT (batch / post-hoc) ----------


def _samp_bucket_key(record: dict[str, Any]) -> tuple[float, float] | None:
    """`sampling.temperature × sampling.top_p` の組をキー化。

    どちらか欠損していたら None (= bucket 評価対象外)。
    """
    sampling = record.get("sampling") or {}
    if not isinstance(sampling, dict):
        return None
    t = sampling.get("temperature")
    p = sampling.get("top_p")
    if not isinstance(t, int | float) or not isinstance(p, int | float):
        return None
    return (float(t), float(p))


def apply_samp_out_filter(
    records: list[dict[str, Any]],
    composites: list[Any],
    *,
    z_min: float = -2.0,
    min_bucket_size: int = 5,
) -> int:
    """`(temperature, top_p)` bucket 内の z-score `< z_min` を SAMP-OUT で hard_reject。

    in-place で `composite.hard_rejected_by` に "SAMP-OUT" を追記し、`signal_versions`
    にも `SAMP-OUT` を記録する。バケットサイズが `min_bucket_size` 未満なら評価をスキップ
    (分布が安定しないため)。戻り値 = 追加棄却件数。

    `composites[i]` には少なくとも `final_score` / `hard_rejected_by` / `signal_versions`
    属性が必要 (CompositeScore 想定だが ducktyping)。
    """
    if len(records) != len(composites):
        raise ValueError("records と composites の長さが一致しません")

    # bucket ごとにインデックスとスコアを集める
    buckets: dict[tuple[float, float], list[int]] = {}
    for i, rec in enumerate(records):
        key = _samp_bucket_key(rec)
        if key is None:
            continue
        buckets.setdefault(key, []).append(i)

    added = 0
    for _key, idxs in buckets.items():
        if len(idxs) < min_bucket_size:
            for i in idxs:
                _annotate_samp_version(composites[i])
            continue
        scores = [float(composites[i].final_score) for i in idxs]
        mean = sum(scores) / len(scores)
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = var**0.5
        if std == 0:
            for i in idxs:
                _annotate_samp_version(composites[i])
            continue
        for i in idxs:
            z = (composites[i].final_score - mean) / std
            _annotate_samp_version(composites[i])
            if z < z_min and SAMP_OUT_CODE not in composites[i].hard_rejected_by:
                composites[i].hard_rejected_by.append(SAMP_OUT_CODE)
                added += 1
    return added


def _annotate_samp_version(composite: Any) -> None:
    """composite.signal_versions に SAMP-OUT のエントリを追加 (記録目的)。"""
    versions = getattr(composite, "signal_versions", None)
    if isinstance(versions, dict):
        versions[SAMP_OUT_CODE] = SAMP_OUT_VERSION


def build_screening_stat_signals(
    th: CurateSignalThresholds,
) -> list[Signal]:
    """健全性スクリーニング用の統計シグナル群 (Epic #305 Phase 1)。

    学習価値向けシグナル (TOOL-*, FACT-HALL 等) は含めない。
    """
    return [
        LenAnswer(th=th),
        LenThinking(th=th),
        ThinkTag(),
        Truncated(),
        EndWell(),
        RepeatNGram(th=th),
        RepeatChar(th=th),
        CtrlChar(),
        LangJapanese(th=th),
        TemplateLeak(),
        SyntaxBreak(),
    ]


def build_default_stat_signals(
    th: CurateSignalThresholds,
    *,
    style_rules: dict[str, StyleRule] | None = None,
) -> list[Signal]:
    """既定の統計シグナル群を組み立てる。

    順序が `scores.jsonl` のシグナル並びになる。決定的な並びを保証するために
    1 ラン内で固定。`SAMP-OUT` は per-record では評価できないので含めない
    (代わりに `apply_samp_out_filter` を CLI 側で post-hoc 適用)。
    """
    return [
        LenAnswer(th=th),
        LenThinking(th=th),
        RatioTA(th=th),
        Truncated(),
        ThinkTag(),
        ToolPlannedNotCalled(),
        ActionClaimWithoutCall(),
        ToolLeak(),
        FactualHallucination(),
        VirtualData(),
        StyleFormat(),
        LangJapanese(th=th),
        RepeatNGram(th=th),
        RepeatChar(th=th),
        DupGlobal(),
        StyleAdherence(th=th, rules=style_rules),
    ]


__all__ = [
    "DupGlobal",
    "LangJapanese",
    "LenAnswer",
    "LenThinking",
    "RatioTA",
    "RepeatChar",
    "RepeatNGram",
    "SAMP_OUT_CODE",
    "SAMP_OUT_VERSION",
    "StyleAdherence",
    "ThinkTag",
    "Truncated",
    "apply_samp_out_filter",
    "build_default_stat_signals",
    "build_screening_stat_signals",
]
