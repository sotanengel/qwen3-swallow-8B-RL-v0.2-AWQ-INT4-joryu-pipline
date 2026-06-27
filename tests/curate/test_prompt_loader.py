"""プロンプトローダのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.curate.prompt_loader import load_health_rubric


def test_load_health_rubric_default():
    loaded = load_health_rubric()
    assert loaded.eval_version == "health_rubric.ja.v1.0"
    assert "L-01" in loaded.text
    assert "{instruction}" in loaded.text


def test_load_health_rubric_from_path(tmp_path: Path):
    p = tmp_path / "custom.txt"
    p.write_text(
        "# version: v2.0\n# eval_version: custom.v2.0\nCustom prompt body\n",
        encoding="utf-8",
    )
    loaded = load_health_rubric(p)
    assert loaded.eval_version == "custom.v2.0"
    assert loaded.text == "Custom prompt body"


def test_load_health_rubric_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_health_rubric(tmp_path / "missing.txt")


def test_load_health_rubric_missing_eval_version(tmp_path: Path):
    p = tmp_path / "bad.txt"
    p.write_text("no header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="eval_version"):
        load_health_rubric(p)
