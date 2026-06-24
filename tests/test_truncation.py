"""truncation.py: 途中打ち切り検出。"""

from joryu.truncation import answer_looks_truncated, record_looks_truncated


def test_answer_ends_with_punctuation_ok() -> None:
    assert answer_looks_truncated("これは完結した文です。") is False


def test_answer_ends_with_header_truncated() -> None:
    assert answer_looks_truncated("導入\n\n## 1. 再犯率の実証的変化") is True


def test_answer_mid_table_truncated() -> None:
    text = "| 項目 | 説明 |\n| 短期収容 | 刑期が短いほど、受"
    assert answer_looks_truncated(text) is True


def test_record_finish_reason_length() -> None:
    assert record_looks_truncated({"finish_reason": "length", "answer": "完結。"}) is True


def test_record_finish_reason_stop() -> None:
    assert record_looks_truncated({"finish_reason": "stop", "answer": "## 見出し"}) is False


def test_record_tool_loop_exhausted_not_truncated() -> None:
    assert record_looks_truncated({"finish_reason": "tool_loop_exhausted", "answer": ""}) is False
