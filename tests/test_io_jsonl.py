"""joryu.io.jsonl のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.io.jsonl import iter_jsonl


def test_iter_jsonl_yields_valid_records(tmp_path: Path) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text(
        '{"a": 1}\n\n{"b": 2}\n',
        encoding="utf-8",
    )
    assert list(iter_jsonl(p)) == [{"a": 1}, {"b": 2}]


def test_iter_jsonl_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text('{"ok": true}\nnot-json\n{"also": 1}\n', encoding="utf-8")
    assert list(iter_jsonl(p)) == [{"ok": True}, {"also": 1}]


def test_iter_jsonl_skips_non_object_lines(tmp_path: Path) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text('[1,2]\n42\n{"x": 1}\n', encoding="utf-8")
    assert list(iter_jsonl(p)) == [{"x": 1}]


def test_iter_jsonl_missing_file_yields_nothing(tmp_path: Path) -> None:
    p = tmp_path / "missing.jsonl"
    assert list(iter_jsonl(p)) == []


def test_iter_jsonl_logs_malformed_when_logger_provided(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    p = tmp_path / "data.jsonl"
    p.write_text("bad\n", encoding="utf-8")
    logger = logging.getLogger("test.io.jsonl")
    with caplog.at_level(logging.WARNING, logger="test.io.jsonl"):
        assert list(iter_jsonl(p, logger=logger, log_prefix="[test]")) == []
    assert "bad" in caplog.text or "malformed" in caplog.text.lower()
