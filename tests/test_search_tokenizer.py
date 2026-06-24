"""search/tokenizer.py のテスト。"""

from __future__ import annotations

from joryu.search.tokenizer import tokenize


def test_tokenize_ascii_words() -> None:
    tokens = tokenize("Hello World test")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens


def test_tokenize_japanese_bigrams() -> None:
    tokens = tokenize("桜の季節")
    assert "桜の" in tokens
    assert "の季" in tokens
    assert "季節" in tokens


def test_tokenize_single_cjk_char() -> None:
    tokens = tokenize("桜")
    assert "桜" in tokens


def test_tokenize_mixed() -> None:
    tokens = tokenize("Pythonで桜を説明")
    assert "python" in tokens
    assert "桜を" in tokens


def test_tokenize_empty() -> None:
    assert tokenize("") == []
    assert tokenize("   ") == []
