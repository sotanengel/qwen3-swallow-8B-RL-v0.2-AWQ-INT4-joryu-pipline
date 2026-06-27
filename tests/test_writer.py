"""writer.py: 追記安全な JSONL writer。"""

import json
from pathlib import Path

from joryu.writer import JsonlAppendWriter


def test_write_one_then_reopen_appends(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "a", "answer": "1"})

    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "b", "answer": "2"})

    lines = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["prompt"] for r in lines] == ["a", "b"]


def test_write_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "deep" / "out.jsonl"
    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "a"})
    assert p.exists()


def test_write_preserves_unicode(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "桜🌸"})
    text = p.read_text(encoding="utf-8")
    assert "桜🌸" in text  # ensure_ascii=False


def test_flush_per_line(tmp_path: Path) -> None:
    # context manager 内でも1行ずつ確実に書き出されることを確認 (resume-safe)
    p = tmp_path / "out.jsonl"
    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "a"})
        # ファイルを別ハンドルから読んで、既に "a" が書き込まれていること
        text = p.read_text(encoding="utf-8")
        assert '"prompt": "a"' in text or '"prompt":"a"' in text
        w.write({"prompt": "b"})

    lines = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_normalize_jsonl_line_strips_control_chars() -> None:
    from joryu.writer import normalize_jsonl_line

    assert normalize_jsonl_line("a\u0001b") == "ab"
    assert normalize_jsonl_line("a\r\nb") == "a\nb"


def test_write_strips_control_chars_from_values(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    with JsonlAppendWriter(p) as w:
        w.write({"prompt": "a\u0001b"})
    line = p.read_text(encoding="utf-8").strip()
    assert "\u0001" not in line
    assert json.loads(line)["prompt"] == "ab"
