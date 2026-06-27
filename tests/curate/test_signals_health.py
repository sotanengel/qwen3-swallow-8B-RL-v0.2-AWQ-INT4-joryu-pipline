"""健全性ルールシグナル (END-WELL / CTRL-CHAR / TPL-LEAK / SYNTAX-BREAK) のテスト。"""

from __future__ import annotations

from joryu.config import CurateSignalThresholds
from joryu.curate.signals.health import (
    CtrlChar,
    EndWell,
    SyntaxBreak,
    TemplateLeak,
    ends_well,
    find_ctrl_char_issue,
    find_syntax_break,
    find_template_leak,
)
from joryu.curate.signals.stat import build_screening_stat_signals


def _rec(**overrides):
    base = {
        "prompt": "説明してください。",
        "answer": "これは正常な回答です。",
        "mode": "nothinking",
    }
    base.update(overrides)
    return base


def test_ends_well_normal_punctuation():
    assert ends_well("正常な文末です。") is True
    assert ends_well("Yes!") is True
    assert ends_well("閉じ括弧）") is True


def test_ends_well_truncated():
    assert ends_well("途中で切れた文") is False
    assert ends_well("") is False


def test_ends_well_code_fence_closed():
    assert ends_well("コード:\n```python\nprint(1)\n```") is True
    assert ends_well("```python\nprint(1)") is False


def test_end_well_signal_ok():
    r = EndWell().evaluate(_rec(answer="問題ありません。"))
    assert r.hard_reject is False
    assert r.score == 1.0


def test_end_well_signal_bad():
    r = EndWell().evaluate(_rec(answer="途中で切れた"))
    assert r.hard_reject is True
    assert r.score == 0.0


def test_ctrl_char_normal():
    assert find_ctrl_char_issue("日本語テキスト") is None


def test_ctrl_char_replacement():
    assert find_ctrl_char_issue("壊れ\ufffd文字") == "replacement_char"


def test_ctrl_char_control():
    assert find_ctrl_char_issue("bad\x00char") == "ctrl:0"


def test_ctrl_char_signal():
    ok = CtrlChar().evaluate(_rec())
    assert ok.hard_reject is False
    bad = CtrlChar().evaluate(_rec(answer="壊れ\ufffd"))
    assert bad.hard_reject is True


def test_tpl_leak_none():
    assert find_template_leak("普通の回答です。") is None


def test_tpl_leak_im_start():
    assert find_template_leak("prefix <|im_start|> user") is not None


def test_tpl_leak_assistant_line():
    assert find_template_leak("text\nassistant\ncontent") is not None


def test_tpl_leak_signal():
    bad = TemplateLeak().evaluate(_rec(answer="leak <|endoftext|>"))
    assert bad.hard_reject is True


def test_syntax_break_fence():
    assert find_syntax_break("```python\nx=1") == "unclosed_fence"


def test_syntax_break_brace():
    assert find_syntax_break("{ unclosed") == "unclosed:}"


def test_syntax_break_ok():
    assert find_syntax_break("正常 {ok}") is None


def test_syntax_break_signal():
    bad = SyntaxBreak().evaluate(_rec(answer="```open"))
    assert bad.hard_reject is True


def test_build_screening_stat_signals_includes_health():
    signals = build_screening_stat_signals(CurateSignalThresholds())
    codes = {s.code for s in signals}
    assert "END-WELL" in codes
    assert "CTRL-CHAR" in codes
    assert "TPL-LEAK" in codes
    assert "SYNTAX-BREAK" in codes
    assert "TOOL-LEAK" not in codes
