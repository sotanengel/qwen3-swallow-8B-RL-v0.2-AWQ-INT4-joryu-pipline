"""stats.py: write_stats_json の書き出し。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.stats import resolve_repo_root, resolve_stats_output_path, write_stats_json


def test_write_stats_json_writes_meta_and_counts(tmp_path: Path) -> None:
    src = tmp_path / "r.jsonl"
    src.write_text(
        json.dumps({"prompt": "P", "answer": "A", "model": "M", "mode": "thinking"}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "stats.json"
    stats = write_stats_json(src, out)
    assert stats["total"] == 1
    assert stats["models"]["M"] == 1
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_meta"]["source_path"] == str(src)
    assert data["_meta"]["generated_at"]


def test_write_stats_json_handles_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "stats.json"
    stats = write_stats_json(tmp_path / "missing.jsonl", out)
    assert stats["total"] == 0
    assert out.exists()


def test_resolve_repo_root_from_distill_out_path(tmp_path: Path) -> None:
    out = tmp_path / "data" / "distilled" / "responses.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    assert resolve_repo_root(out_path=out) == tmp_path.resolve()


def test_resolve_stats_output_path_uses_joryu_repo_root_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JORYU_REPO_ROOT", str(tmp_path))
    out = resolve_stats_output_path()
    assert out == tmp_path / "dashboard" / "public" / "stats.json"


def test_resolve_repo_root_returns_none_for_custom_out_path(tmp_path: Path) -> None:
    out = tmp_path / "custom" / "out.jsonl"
    assert resolve_repo_root(out_path=out) is None


def test_resolve_limits_probe_path_uses_repo_root(tmp_path: Path, monkeypatch) -> None:
    from joryu.paths import resolve_limits_probe_path

    monkeypatch.setenv("JORYU_REPO_ROOT", str(tmp_path))
    resolved = resolve_limits_probe_path("data/vllm_limits.json")
    assert resolved == (tmp_path / "data" / "vllm_limits.json").resolve()
