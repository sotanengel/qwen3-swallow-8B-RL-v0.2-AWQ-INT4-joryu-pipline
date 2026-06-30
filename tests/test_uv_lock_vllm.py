"""uv.lock の vLLM セキュリティ pin 契約テスト (Dependabot #3-#7, Closes #377)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UV_LOCK = REPO_ROOT / "uv.lock"

_VLLM_BLOCK_RE = re.compile(
    r'\[\[package\]\]\nname = "vllm"\nversion = "([^"]+)"\nsource = (\{[^}]+\})',
)


def _vllm_lock_entry() -> tuple[str, str]:
    text = UV_LOCK.read_text(encoding="utf-8")
    match = _VLLM_BLOCK_RE.search(text)
    assert match is not None, "uv.lock must contain a vllm package entry"
    return match.group(1), match.group(2)


def test_uv_lock_vllm_is_git_sourced() -> None:
    _version, source = _vllm_lock_entry()
    assert "git" in source
    assert "v0.23.1rc0" in source
    assert "registry" not in source


def test_uv_lock_vllm_not_vulnerable_pypi_release() -> None:
    version, _source = _vllm_lock_entry()
    assert version != "0.23.0"
