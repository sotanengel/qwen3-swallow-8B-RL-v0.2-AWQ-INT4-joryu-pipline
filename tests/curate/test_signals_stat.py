"""統計シグナル個別ユニットテスト (R-10)。"""

from __future__ import annotations

from joryu.config import CurateSignalThresholds
from joryu.curate.scoring import CompositeScore
from joryu.curate.signals.stat import (
    SAMP_OUT_CODE,
    SAMP_OUT_VERSION,
    DupGlobal,
    LangJapanese,
    LenAnswer,
    LenThinking,
    RatioTA,
    RepeatChar,
    RepeatNGram,
    StyleAdherence,
    ThinkTag,
    Truncated,
    apply_samp_out_filter,
    build_default_stat_signals,
)
from joryu.curate.style_presets import DEFAULT_STYLE_RULES


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


def test_truncated_heuristic_header_end():
    sig = Truncated()
    r = sig.evaluate(_rec(answer="導入\n\n## 1. 再犯率"))
    assert r.hard_reject is True
    assert r.raw == "heuristic"


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
        "STYLE-ADH",
    ]


# ---------- STYLE-ADH ----------


def test_style_adh_no_style_id_returns_neutral():
    sig = StyleAdherence(th=CurateSignalThresholds(), rules=DEFAULT_STYLE_RULES)
    r = sig.evaluate(_rec(answer="どんな文体でも。"))
    assert r.hard_reject is False
    assert r.score == 1.0


def test_style_adh_unknown_style_returns_neutral():
    sig = StyleAdherence(th=CurateSignalThresholds(), rules=DEFAULT_STYLE_RULES)
    r = sig.evaluate(_rec(style_id="unknown_preset", answer="something"))
    assert r.hard_reject is False
    assert r.score == 1.0


# ---------- SAMP-OUT (batch) ----------


def _make_composite(final_score: float) -> CompositeScore:
    return CompositeScore(
        stat_score=final_score,
        llm_score=None,
        final_score=final_score,
        hard_rejected_by=[],
        signal_versions={},
        signal_scores={},
        signal_raw={},
    )


def test_samp_out_marks_low_outlier_in_bucket():
    # 同一 (temperature=0.6, top_p=0.95) bucket に 6 件、うち 1 件だけ極端に低い
    records = [_rec(sampling={"temperature": 0.6, "top_p": 0.95}) for _ in range(6)]
    composites = [_make_composite(0.8) for _ in range(5)] + [_make_composite(0.1)]
    added = apply_samp_out_filter(records, composites, z_min=-1.5, min_bucket_size=3)
    assert added == 1
    assert SAMP_OUT_CODE in composites[-1].hard_rejected_by
    assert all(SAMP_OUT_CODE not in c.hard_rejected_by for c in composites[:-1])


def test_samp_out_skip_small_bucket():
    records = [_rec(sampling={"temperature": 0.6, "top_p": 0.95}) for _ in range(3)]
    composites = [_make_composite(0.8), _make_composite(0.85), _make_composite(0.1)]
    added = apply_samp_out_filter(records, composites, z_min=-1.0, min_bucket_size=5)
    assert added == 0  # bucket size 3 < 5 なので評価 skip


def test_samp_out_records_signal_version():
    records = [_rec(sampling={"temperature": 0.6, "top_p": 0.95}) for _ in range(2)]
    composites = [_make_composite(0.8), _make_composite(0.8)]
    apply_samp_out_filter(records, composites, min_bucket_size=2)
    for c in composites:
        assert c.signal_versions.get(SAMP_OUT_CODE) == SAMP_OUT_VERSION


def test_samp_out_ignores_records_without_sampling():
    records = [_rec(sampling=None), _rec(sampling={"temperature": 0.6, "top_p": 0.95})]
    composites = [_make_composite(0.5), _make_composite(0.8)]
    added = apply_samp_out_filter(records, composites, min_bucket_size=1)
    # sampling 欠損は bucket 評価対象外。残り 1 件だけ bucket だが std=0 → 追加棄却なし
    assert added == 0
