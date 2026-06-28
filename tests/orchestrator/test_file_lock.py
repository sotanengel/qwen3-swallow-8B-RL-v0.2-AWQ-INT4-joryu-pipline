"""file_lock テスト。"""

from __future__ import annotations

from pathlib import Path

from joryu.orchestrator.file_lock import file_lock


def test_file_lock_allows_sequential_writes(tmp_path: Path) -> None:
    target = tmp_path / "data" / "active_profile.json"
    with file_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"status":"active"}\n', encoding="utf-8")
    assert target.read_text(encoding="utf-8").startswith("{")
