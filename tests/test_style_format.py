"""style_format.py: 出力形式メトリクスのヒューリスティック。"""

from joryu.style_format import (
    aggregate_by_style,
    check_style_format_criteria,
    format_metrics,
    has_markdown_markers,
    sentence_count,
)


def test_has_markdown_markers_plain_prose() -> None:
    text = "桜は春に咲く木です。花びらが美しいです。"
    assert has_markdown_markers(text) is False


def test_has_markdown_markers_dialog_plain() -> None:
    text = "そうですね、東京は日本の首都です。ぜひ訪れてみてください。"
    assert has_markdown_markers(text) is False


def test_has_markdown_markers_report_style() -> None:
    text = "## 概要\n\n- 項目1\n- 項目2\n\n| 列A | 列B |\n|---|---|\n| a | b |\n\n**結論**"
    assert has_markdown_markers(text) is True


def test_has_markdown_markers_header_only() -> None:
    assert has_markdown_markers("## 見出し\n本文です。") is True


def test_has_markdown_markers_bullet_only() -> None:
    assert has_markdown_markers("- 箇条書き項目") is True


def test_has_markdown_markers_numbered_list() -> None:
    assert has_markdown_markers("1. 最初の項目\n2. 二番目") is True


def test_has_markdown_markers_bold_only() -> None:
    assert has_markdown_markers("これは**重要**です。") is True


def test_has_markdown_markers_table_pipe() -> None:
    assert has_markdown_markers("| col1 | col2 |") is True


def test_sentence_count_two_to_four() -> None:
    text = "一つ目の文です。二つ目の文です。三つ目。"
    assert sentence_count(text) == 3


def test_sentence_count_empty() -> None:
    assert sentence_count("") == 0
    assert sentence_count("   ") == 0


def test_format_metrics_keys() -> None:
    text = "短い回答です。"
    m = format_metrics(text)
    assert m == {
        "has_markdown": False,
        "sentence_count": 1,
        "char_count": len(text),
    }


def test_aggregate_by_style_groups_records() -> None:
    records = [
        {"style_id": "dialog", "answer": "一つ目。二つ目。"},
        {"style_id": "dialog", "answer": "## 見出し\n- item"},
        {"style_id": "prose", "answer": "散文です。"},
        {"style_id": None, "answer": "ignored"},
    ]
    agg = aggregate_by_style(records)
    assert agg["dialog"]["count"] == 2.0
    assert agg["dialog"]["md_marker_rate"] == 0.5
    assert agg["dialog"]["mean_sentence_count"] == 2.0
    assert agg["prose"]["md_marker_rate"] == 0.0


def test_check_style_format_criteria_passes_ideal_sample() -> None:
    aggregates = {
        "dialog": {"md_marker_rate": 0.0, "mean_sentence_count": 3.0},
        "prose": {"md_marker_rate": 0.05, "mean_sentence_count": 4.0},
        "qa_short": {"md_marker_rate": 0.0, "mean_sentence_count": 2.0},
        "report": {"md_marker_rate": 0.9, "mean_sentence_count": 8.0},
    }
    assert check_style_format_criteria(aggregates) == []


def test_check_style_format_criteria_detects_y1_violation() -> None:
    aggregates = {
        "dialog": {"md_marker_rate": 0.5, "mean_sentence_count": 3.0},
        "prose": {"md_marker_rate": 0.1, "mean_sentence_count": 4.0},
    }
    errors = check_style_format_criteria(aggregates)
    assert any("Y1" in e for e in errors)
