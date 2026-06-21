"""progress.py: 既存 JSONL から処理済 prompt の集合を抽出する。"""

import json
from pathlib import Path

from joryu.progress import load_done_prompts


def test_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_done_prompts(tmp_path / "x.jsonl") == set()


def test_returns_empty_when_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text("", encoding="utf-8")
    assert load_done_prompts(p) == set()


def test_collects_prompts(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"prompt": "a", "answer": "x"}, ensure_ascii=False),
                json.dumps({"prompt": "b", "answer": "y"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_done_prompts(p) == {"a", "b"}


def test_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"prompt": "a"}),
                "not-json",
                "",
                json.dumps({"answer": "no prompt"}),
                json.dumps({"prompt": ""}),
                json.dumps({"prompt": "b"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_done_prompts(p) == {"a", "b"}
