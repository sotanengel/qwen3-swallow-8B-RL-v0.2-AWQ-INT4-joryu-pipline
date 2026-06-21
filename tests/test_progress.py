"""progress.py: 既存 JSONL から処理済 run キーの集合を抽出する。"""

import json
from pathlib import Path

from joryu.config import Config
from joryu.progress import load_done_keys, run_key_from_parts, run_key_from_record


def test_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_done_keys(tmp_path / "x.jsonl") == set()


def test_returns_empty_when_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text("", encoding="utf-8")
    assert load_done_keys(p) == set()


def test_collects_run_keys(tmp_path: Path) -> None:
    cfg = Config()
    p = tmp_path / "out.jsonl"
    key_a = run_key_from_parts(
        prompt="a",
        style_id=None,
        mode=cfg.model.mode,
        temperature=cfg.model.temperature,
        top_p=cfg.model.top_p,
    )
    key_b = run_key_from_parts(
        prompt="b",
        style_id="polite",
        mode=cfg.model.mode,
        temperature=0.7,
        top_p=0.9,
    )
    p.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "a",
                        "mode": cfg.model.mode,
                        "sampling": {
                            "temperature": cfg.model.temperature,
                            "top_p": cfg.model.top_p,
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "prompt": "b",
                        "style_id": "polite",
                        "mode": cfg.model.mode,
                        "sampling": {"temperature": 0.7, "top_p": 0.9},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_done_keys(p) == {key_a, key_b}


def test_same_prompt_different_style_is_distinct_key() -> None:
    cfg = Config()
    key_default = run_key_from_parts(
        prompt="p",
        style_id=None,
        mode=cfg.model.mode,
        temperature=cfg.model.temperature,
        top_p=cfg.model.top_p,
    )
    key_polite = run_key_from_parts(
        prompt="p",
        style_id="polite",
        mode=cfg.model.mode,
        temperature=cfg.model.temperature,
        top_p=cfg.model.top_p,
    )
    assert key_default != key_polite


def test_skips_malformed_lines(tmp_path: Path) -> None:
    cfg = Config()
    p = tmp_path / "out.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "a",
                        "mode": cfg.model.mode,
                        "sampling": {
                            "temperature": cfg.model.temperature,
                            "top_p": cfg.model.top_p,
                        },
                    }
                ),
                "not-json",
                "",
                json.dumps({"answer": "no prompt"}),
                json.dumps({"prompt": ""}),
                json.dumps(
                    {
                        "prompt": "b",
                        "mode": cfg.model.mode,
                        "sampling": {
                            "temperature": cfg.model.temperature,
                            "top_p": cfg.model.top_p,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert len(load_done_keys(p)) == 2


def test_run_key_from_record_round_trip() -> None:
    rec = {
        "prompt": "x",
        "style_id": "casual",
        "mode": "nothinking",
        "sampling": {"temperature": 0.8, "top_p": 0.85},
    }
    key = run_key_from_record(rec)
    assert key is not None
    assert '"prompt": "x"' in key
    assert '"style_id": "casual"' in key
