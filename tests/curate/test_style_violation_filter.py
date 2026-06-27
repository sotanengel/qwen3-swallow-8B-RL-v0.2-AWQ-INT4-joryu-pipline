"""Style 違反フィルタ (#298 / Epic #294 Sub#4)。"""

from __future__ import annotations

from joryu.curate.signals.quality import StyleFormat


def _rec(**overrides):
    base = {"prompt": "p", "answer": "短い回答です。", "style_id": "prose"}
    base.update(overrides)
    return base


def test_prose_rejects_markdown_hrule() -> None:
    sig = StyleFormat()
    ok = sig.evaluate(_rec(style_id="prose", answer="自然な散文です。"))
    bad = sig.evaluate(_rec(style_id="prose", answer="前文\n---\n後文"))
    assert ok.hard_reject is False
    assert bad.hard_reject is True


def test_prose_rejects_bold() -> None:
    sig = StyleFormat()
    r = sig.evaluate(_rec(style_id="prose", answer="これは**強調**です。"))
    assert r.hard_reject is True


def test_qa_short_rejects_long_answer() -> None:
    sig = StyleFormat()
    ok = sig.evaluate(_rec(style_id="qa_short", answer="短答。"))
    bad = sig.evaluate(_rec(style_id="qa_short", answer="あ" * 201))
    assert ok.hard_reject is False
    assert bad.hard_reject is True


def test_qa_short_rejects_bold() -> None:
    sig = StyleFormat()
    r = sig.evaluate(_rec(style_id="qa_short", answer="**結論**です。"))
    assert r.hard_reject is True


def test_dialog_rejects_think_tags() -> None:
    think_leak = "<" + "redacted_thinking" + ">\nEnglish reasoning"
    sig = StyleFormat()
    r = sig.evaluate(_rec(style_id="dialog", answer=think_leak))
    assert r.hard_reject is True


def test_report_allows_markdown() -> None:
    sig = StyleFormat()
    r = sig.evaluate(_rec(style_id="report", answer="# 見出し\n- 箇条書き"))
    assert r.hard_reject is False


def test_all_styles_reject_phrase_triple_repeat() -> None:
    sig = StyleFormat()
    repeated = "同じフレーズABC" * 3
    for style_id in ("prose", "qa_short", "dialog"):
        r = sig.evaluate(_rec(style_id=style_id, answer=repeated))
        assert r.hard_reject is True, style_id
    report_ok = sig.evaluate(_rec(style_id="report", answer=repeated))
    assert report_ok.hard_reject is True


def test_prose_accepts_plain_paragraph() -> None:
    sig = StyleFormat()
    r = sig.evaluate(
        _rec(
            style_id="prose",
            answer="今日の東京は晴れで、気温は快適な範囲に収まる見込みです。",
        )
    )
    assert r.hard_reject is False
