"""joryu-curate 逐次書き込みのスモークテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.cli import curate as cli


def _make_input(tmp_path: Path, n: int = 5) -> Path:
    src = tmp_path / "responses.jsonl"
    records = [
        {
            "prompt": f"質問{i}",
            "answer": f"回答{i}。桜は春に咲く日本の代表的な花です。" * 2,
            "mode": "nothinking",
            "sampling": {"temperature": 0.6, "top_p": 0.95},
            "system_prompt": "あなたは日本語アシスタントです。",
            "config_hash": "sha256-test",
            "style_id": "prose",
            "category": "国語",
        }
        for i in range(n)
    ]
    src.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return src


def test_curate_streaming_writes_scores_incrementally(tmp_path: Path) -> None:
    src = _make_input(tmp_path, n=3)
    dst = tmp_path / "curated"
    rc = cli.main(
        ["--src", str(src), "--dst", str(dst), "--threshold", "0.0", "--skip-llm"],
    )
    assert rc == 0
    scores = dst / "scores.jsonl"
    assert scores.exists()
    lines = scores.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert (dst / "responses.high_quality.jsonl").exists()
    meta = json.loads((dst / "curation_meta.json").read_text(encoding="utf-8"))
    assert meta["summary"]["kept"] + meta["summary"]["rejected"] == 3
