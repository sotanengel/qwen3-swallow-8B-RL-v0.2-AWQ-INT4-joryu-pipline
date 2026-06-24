"""search/snippets.py のテスト。"""

from __future__ import annotations

from joryu.search.snippets import extract_snippet, pick_snippet_field


def test_extract_snippet_around_match() -> None:
    text = "あ" * 100 + "桜" + "い" * 100
    snippet = extract_snippet(text, "桜", max_chars=40)
    assert "桜" in snippet


def test_extract_snippet_short_text() -> None:
    assert extract_snippet("短いテキスト", "テキ", max_chars=200) == "短いテキスト"


def test_pick_snippet_field_prefers_answer() -> None:
    rec = {
        "prompt": "質問",
        "answer": "桜について詳しく説明します",
        "thinking_trace": "考え中",
    }
    field = pick_snippet_field(rec, "桜")
    assert field == "answer"
