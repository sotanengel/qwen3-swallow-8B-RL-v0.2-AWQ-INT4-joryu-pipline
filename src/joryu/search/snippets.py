"""検索結果スニペット抽出。"""

from __future__ import annotations

from typing import Any

_SEARCHABLE_FIELDS = ("answer", "prompt", "thinking_trace", "category", "style_id", "model")


def pick_snippet_field(record: dict[str, Any], query: str) -> str:
    """クエリ文字列が最も多く含まれるフィールド名を返す。"""
    q = query.strip().lower()
    if not q:
        return "answer" if record.get("answer") else "prompt"

    best_field = "prompt"
    best_count = -1
    for field in _SEARCHABLE_FIELDS:
        value = str(record.get(field) or "")
        if not value:
            continue
        lowered = value.lower()
        count = sum(1 for term in q.split() if term and term in lowered)
        if count == 0:
            count = 1 if q in lowered else 0
        if count > best_count:
            best_count = count
            best_field = field
    return best_field


def extract_snippet(text: str, query: str, *, max_chars: int = 200) -> str:
    """マッチ箇所周辺のテキストを切り出す。"""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    q = query.strip()
    if not q:
        return text[: max_chars - 1] + "…"

    lowered = text.lower()
    pos = -1
    for term in q.split():
        if not term:
            continue
        idx = lowered.find(term.lower())
        if idx >= 0:
            pos = idx
            break
    if pos < 0:
        for term in q:
            idx = lowered.find(term.lower())
            if idx >= 0:
                pos = idx
                break

    if pos < 0:
        return text[: max_chars - 1] + "…"

    half = max_chars // 2
    start = max(0, pos - half)
    end = min(len(text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    snippet = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"
