"""STYLE-ADH シグナル用の文体プリセット規則 (R-10)。

`styles.yaml` で宣言されたプリセットに対し、文末規則 + キーワードの 2 軸で
adherence (一致率) を計算する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class StyleRule:
    """1 文体プリセットの判定規則。"""

    style_id: str
    sentence_end_patterns: tuple[re.Pattern[str], ...]
    keywords: tuple[str, ...] = ()
    min_adherence: float = 0.3

    def adherence(self, text: str) -> float:
        """テキスト全体の文体一致率 [0,1]。

        - 文を `。 ！ ？ 改行` で分割し、文末規則のいずれかにマッチした文の割合 (重み 0.7)
        - キーワードヒット率 (重み 0.3)。キーワード未定義なら sentence_ratio のみ。
        """
        sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
        if not sentences:
            return 0.0
        sentence_matches = sum(
            1 for s in sentences if any(p.search(s) for p in self.sentence_end_patterns)
        )
        sentence_ratio = sentence_matches / len(sentences)
        if not self.keywords:
            return sentence_ratio
        kw_hits = sum(1 for k in self.keywords if k in text)
        kw_ratio = min(1.0, kw_hits / len(self.keywords))
        return 0.7 * sentence_ratio + 0.3 * kw_ratio


DEFAULT_STYLE_RULES: dict[str, StyleRule] = {
    "polite": StyleRule(
        style_id="polite",
        sentence_end_patterns=(
            re.compile(r"です$"),
            re.compile(r"ます$"),
            re.compile(r"でしょう$"),
            re.compile(r"ました$"),
            re.compile(r"ません$"),
            re.compile(r"ですね$"),
            re.compile(r"ですよ$"),
        ),
        keywords=("ございます", "いたします", "申し上げ"),
        min_adherence=0.4,
    ),
    "casual": StyleRule(
        style_id="casual",
        sentence_end_patterns=(
            re.compile(r"[だよねかな]$"),
            re.compile(r"だね$"),
            re.compile(r"だよ$"),
            re.compile(r"かな$"),
            re.compile(r"るよ$"),
            re.compile(r"るね$"),
        ),
        keywords=("だよ", "じゃん", "って感じ"),
        min_adherence=0.25,
    ),
    "expert": StyleRule(
        style_id="expert",
        sentence_end_patterns=(
            re.compile(r"である$"),
            re.compile(r"られる$"),
            re.compile(r"考えられる$"),
            re.compile(r"といえる$"),
            re.compile(r"とされる$"),
        ),
        keywords=("したがって", "すなわち", "ゆえに", "一方", "本研究", "本稿"),
        min_adherence=0.2,
    ),
}


def load_style_rules(
    styles_yaml: str | Path | None = None,
    *,
    overrides: dict[str, StyleRule] | None = None,
) -> dict[str, StyleRule]:
    """`styles.yaml` で宣言されたプリセットに対応する `StyleRule` 辞書を返す。

    - `styles.yaml` 未指定 / 不在の場合は `DEFAULT_STYLE_RULES` 全件
    - YAML に書かれた `styles.<id>` のうち、`DEFAULT_STYLE_RULES` に定義のあるものだけ拾う
    - `overrides` で個別ルール差し替え可能 (テスト用)
    """
    rules: dict[str, StyleRule]
    if styles_yaml is None:
        rules = dict(DEFAULT_STYLE_RULES)
    else:
        p = Path(styles_yaml)
        if not p.exists():
            rules = dict(DEFAULT_STYLE_RULES)
        else:
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            declared = raw.get("styles") or {}
            rules = {
                sid: DEFAULT_STYLE_RULES[sid] for sid in declared if sid in DEFAULT_STYLE_RULES
            }
            if not rules:
                rules = dict(DEFAULT_STYLE_RULES)
    if overrides:
        rules.update(overrides)
    return rules


__all__ = [
    "DEFAULT_STYLE_RULES",
    "StyleRule",
    "load_style_rules",
]
