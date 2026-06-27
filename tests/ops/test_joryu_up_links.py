"""joryu-up dashboard link tests (#254)."""

from __future__ import annotations

from pathlib import Path

import pytest

from joryu.preflight import ensure_dashboard_data_paths, sync_dashboard_responses_copy


@pytest.fixture
def repo_layout(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    return tmp_path


def test_ensure_dashboard_data_paths_repairs_zero_byte_public_jsonl(
    repo_layout: Path,
) -> None:
    jsonl_path = repo_layout / "data" / "distilled" / "responses.jsonl"
    jsonl_path.parent.mkdir(parents=True)
    jsonl_path.write_text('{"prompt":"hello","answer":"world"}\n', encoding="utf-8")

    public_jsonl = repo_layout / "dashboard" / "public" / "responses.jsonl"
    public_jsonl.parent.mkdir(parents=True)
    public_jsonl.write_text("", encoding="utf-8")

    ensure_dashboard_data_paths(repo_layout)

    assert public_jsonl.stat().st_size > 0
    if public_jsonl.is_symlink():
        assert public_jsonl.resolve() == jsonl_path.resolve()
    else:
        assert public_jsonl.read_text(encoding="utf-8") == jsonl_path.read_text(encoding="utf-8")


def test_ensure_dashboard_data_paths_copy_fallback_when_symlink_fails(
    repo_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jsonl_path = repo_layout / "data" / "distilled" / "responses.jsonl"
    jsonl_path.parent.mkdir(parents=True)
    jsonl_path.write_text('{"prompt":"x"}\n', encoding="utf-8")

    def _fail_symlink(*_args, **_kwargs) -> None:
        raise OSError("symlink unsupported")

    monkeypatch.setattr(Path, "symlink_to", _fail_symlink, raising=False)

    ensure_dashboard_data_paths(repo_layout)

    public_jsonl = repo_layout / "dashboard" / "public" / "responses.jsonl"
    assert public_jsonl.is_file()
    assert not public_jsonl.is_symlink()
    assert public_jsonl.read_text(encoding="utf-8") == jsonl_path.read_text(encoding="utf-8")


def test_sync_dashboard_responses_copy_updates_public_file(
    repo_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jsonl_path = repo_layout / "data" / "distilled" / "responses.jsonl"
    jsonl_path.parent.mkdir(parents=True)
    jsonl_path.write_text('{"prompt":"a"}\n', encoding="utf-8")

    def _fail_symlink(*_args, **_kwargs) -> None:
        raise OSError("symlink unsupported")

    monkeypatch.setattr(Path, "symlink_to", _fail_symlink, raising=False)
    ensure_dashboard_data_paths(repo_layout)

    jsonl_path.write_text(
        jsonl_path.read_text(encoding="utf-8") + '{"prompt":"b"}\n',
        encoding="utf-8",
    )
    sync_dashboard_responses_copy(repo_layout)

    public_jsonl = repo_layout / "dashboard" / "public" / "responses.jsonl"
    assert public_jsonl.read_text(encoding="utf-8") == jsonl_path.read_text(encoding="utf-8")
