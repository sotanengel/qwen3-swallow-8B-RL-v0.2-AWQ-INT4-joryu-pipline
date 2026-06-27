"""prompt_dedup.py のテスト (#235)。"""

from __future__ import annotations

from joryu.prompt_dedup import PromptDedupGuard, normalize_prompt


def test_normalize_prompt_nfkc() -> None:
    assert normalize_prompt("　今日の東京の天気は？　") == "今日の東京の天気は?"


def test_prompt_dedup_guard_limits_per_key() -> None:
    guard = PromptDedupGuard(max_per_key=5)
    prompt = "今日の東京の天気は？"
    for _ in range(5):
        assert guard.should_skip(prompt=prompt, style_id="prose") is False
        guard.record(prompt=prompt, style_id="prose")
    assert guard.should_skip(prompt=prompt, style_id="prose") is True
    assert guard.should_skip(prompt=prompt, style_id="dialog") is False
