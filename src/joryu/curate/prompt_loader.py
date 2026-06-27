"""外部プロンプトファイルのロード (健全性 rubric 等)。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from joryu.paths import resolve_repo_root

_EVAL_VERSION_RE = re.compile(r"^#\s*eval_version:\s*(\S+)", re.MULTILINE)
_VERSION_RE = re.compile(r"^#\s*version:\s*(\S+)", re.MULTILINE)

DEFAULT_HEALTH_RUBRIC_REL = "prompts/health_rubric.ja.txt"

_CACHE: dict[str, LoadedPrompt] = {}


@dataclass(frozen=True)
class LoadedPrompt:
    """ロード済みプロンプト + メタデータ。"""

    text: str
    eval_version: str
    version: str
    path: Path


def _parse_prompt_file(path: Path) -> LoadedPrompt:
    raw = path.read_text(encoding="utf-8")
    eval_m = _EVAL_VERSION_RE.search(raw)
    ver_m = _VERSION_RE.search(raw)
    if eval_m is None:
        raise ValueError(f"eval_version header missing in prompt file: {path}")
    # ヘッダコメント行を除去して本文のみ
    body_lines: list[str] = []
    for line in raw.splitlines():
        if line.strip().startswith("#"):
            continue
        body_lines.append(line)
    text = "\n".join(body_lines).strip()
    return LoadedPrompt(
        text=text,
        eval_version=eval_m.group(1),
        version=ver_m.group(1) if ver_m else "unknown",
        path=path,
    )


def _default_health_rubric_path() -> Path:
    """リポジトリ内の既定プロンプトパスを解決。"""
    here = Path(__file__).resolve()
    for base in (here.parents[3], *([] if resolve_repo_root() is None else [resolve_repo_root()])):
        candidate = Path(base) / DEFAULT_HEALTH_RUBRIC_REL
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"health rubric prompt not found at {DEFAULT_HEALTH_RUBRIC_REL}")


def load_health_rubric(path: Path | None = None) -> LoadedPrompt:
    """健全性 LLM rubric プロンプトをロード (キャッシュ付き)。"""
    if path is not None:
        key = str(path.resolve())
        if key not in _CACHE:
            if not path.is_file():
                raise FileNotFoundError(f"health rubric prompt not found: {path}")
            _CACHE[key] = _parse_prompt_file(path)
        return _CACHE[key]

    default_key = "default"
    if default_key in _CACHE:
        return _CACHE[default_key]

    resolved = _default_health_rubric_path()
    loaded = _parse_prompt_file(resolved)
    _CACHE[default_key] = loaded
    return loaded


__all__ = [
    "DEFAULT_HEALTH_RUBRIC_REL",
    "LoadedPrompt",
    "load_health_rubric",
]
