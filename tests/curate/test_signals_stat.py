"""統計シグナル個別ユニットテスト (R-10)。"""

from __future__ import annotations

from joryu.config import CurateSignalThresholds
from joryu.curate.signals.stat import (
    DupGlobal,
    LangJapanese,
    LenAnswer,
    LenThinking,
    RatioTA,
    RepeatChar,
    RepeatNGram,
    ThinkTag,
    Truncated,
    build_default_stat_signals,
)


def _rec(**overrides):
    base = {
        "prompt": "p",
        "answer": "あ" * 100,
        "mode": "nothinking",
        "sampling": {"temperature": 0.6},
        "config_hash": "h",
    }
    base.update(overrides)
    return base


def test_len_answer_short_is_hard_rejected():
    th = CurateSignalThresholds()
    sig = LenAnswer(th=th)
    r = sig.evaluate(_rec(answer="短い"))
    assert r.hard_reject is True


def test_len_answer_in_range_is_not_rejected():
    th = CurateSignalThresholds()
    sig = LenAnswer(th=th)
    r = sig.evaluate(_rec(answer="あ" * 100))
    assert r.hard_reject is False
    assert 0.0 <= r.score <= 1.0


def test_len_answer_too_long_is_rejected():
    th = CurateSignalThresholds()
    sig = LenAnswer(th=th)
    r = sig.evaluate(_rec(answer="あ" * 5000))
    assert r.hard_reject is True


def test_len_thinking_skipped_when_nothinking_mode():
    sig = LenThinking(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(mode="nothinking", thinking_trace=None))
    assert r.hard_reject is False
    assert r.score == 1.0


def test_len_thinking_too_short_is_rejected():
    sig = LenThinking(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(mode="thinking", thinking_trace=""))
    assert r.hard_reject is True


def test_ratio_ta_out_of_band():
    sig = RatioTA(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(mode="thinking", thinking_trace="あ" * 100000, answer="あ" * 10))
    assert r.hard_reject is True


def test_truncated_finish_reason_length():
    sig = Truncated()
    r = sig.evaluate(_rec(finish_reason="length"))
    assert r.hard_reject is True


def test_truncated_finish_reason_stop_ok():
    sig = Truncated()
    r = sig.evaluate(_rec(finish_reason="stop"))
    assert r.hard_reject is False


def test_think_tag_symmetric_when_nothinking_passes():
    sig = ThinkTag()
    r = sig.evaluate(_rec(mode="nothinking", answer="ok"))
    assert r.hard_reject is False


def test_think_tag_unbalanced_in_thinking_mode_rejected():
    sig = ThinkTag()
    r = sig.evaluate(_rec(mode="thinking", answer="<think>x", thinking_trace=""))
    assert r.hard_reject is True


def test_lang_ja_pure_japanese():
    sig = LangJapanese(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(answer="日本語の文章です。"))
    assert r.hard_reject is False
    assert r.score >= 0.6


def test_lang_ja_too_much_english_rejected():
    sig = LangJapanese(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(answer="this is mostly english text only"))
    assert r.hard_reject is True


def test_lang_ja_empty_rejected():
    sig = LangJapanese(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(answer=""))
    assert r.hard_reject is True


def test_repeat_ngram_detects_loop():
    sig = RepeatNGram(th=CurateSignalThresholds())
    looped = "おはようございます。" * 50
    r = sig.evaluate(_rec(answer=looped))
    assert r.hard_reject is True


def test_repeat_ngram_normal_text_ok():
    sig = RepeatNGram(th=CurateSignalThresholds())
    normal = "今日は良い天気ですね。明日は雨が降るそうです。週末には晴れる予報です。"
    r = sig.evaluate(_rec(answer=normal))
    assert r.hard_reject is False


def test_repeat_char_long_run_rejected():
    sig = RepeatChar(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(answer="あ" * 100))
    assert r.hard_reject is True


def test_repeat_char_short_run_ok():
    sig = RepeatChar(th=CurateSignalThresholds())
    r = sig.evaluate(_rec(answer="あいうえお" * 10))
    assert r.hard_reject is False


def test_dup_global_first_time_passes():
    sig = DupGlobal()
    r = sig.evaluate(_rec(answer="unique"))
    assert r.hard_reject is False


def test_dup_global_second_time_rejected():
    sig = DupGlobal()
    sig.evaluate(_rec(answer="dup"))
    r2 = sig.evaluate(_rec(answer="dup"))
    assert r2.hard_reject is True


def test_dup_global_empty_answer_rejected():
    sig = DupGlobal()
    r = sig.evaluate(_rec(answer=""))
    assert r.hard_reject is True


def test_build_default_stat_signals_returns_all_codes():
    sigs = build_default_stat_signals(CurateSignalThresholds())
    codes = [s.code for s in sigs]
    assert codes == [
        "LEN-A",
        "LEN-T",
        "RATIO-TA",
        "TRUNC",
        "THINK-TAG",
        "LANG-JA",
        "REPEAT-NG",
        "REPEAT-CHAR",
        "DUP-GLOB",
    ]
