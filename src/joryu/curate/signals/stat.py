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

from . import Signal, SignalResult

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
    version: str = "v1"

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        fr = record.get("finish_reason")
        truncated = fr == "length"
        return SignalResult(
            self.code, self.version, 0.0 if truncated else 1.0, fr, hard_reject=truncated
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
    """同一ラン内の `answer` 完全重複検出。

    MVP では MinHash 永続化なしで、1 ラン内の SHA1 短縮ハッシュ集合のみを保持する。
    本要件 R-24 (MinHash 永続化 + ラン跨ぎ) は後続 PR で実装。
    """

    code = "DUP-GLOB"
    version = "v1"

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def evaluate(self, record: dict[str, Any]) -> SignalResult:
        text = (record.get("answer") or "").strip()
        if not text:
            return SignalResult(self.code, self.version, 0.0, "empty", True)
        h = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()
        if h in self._seen:
            return SignalResult(self.code, self.version, 0.0, h, True)
        self._seen.add(h)
        return SignalResult(self.code, self.version, 1.0, h, False)


def build_default_stat_signals(th: CurateSignalThresholds) -> list[Signal]:
    """既定の統計シグナル群を組み立てる。

    順序が `scores.jsonl` のシグナル並びになる。決定的な並びを保証するために
    1 ラン内で固定。
    """
    return [
        LenAnswer(th=th),
        LenThinking(th=th),
        RatioTA(th=th),
        Truncated(),
        ThinkTag(),
        LangJapanese(th=th),
        RepeatNGram(th=th),
        RepeatChar(th=th),
        DupGlobal(),
    ]


__all__ = [
    "DupGlobal",
    "LangJapanese",
    "LenAnswer",
    "LenThinking",
    "RatioTA",
    "RepeatChar",
    "RepeatNGram",
    "ThinkTag",
    "Truncated",
    "build_default_stat_signals",
]
