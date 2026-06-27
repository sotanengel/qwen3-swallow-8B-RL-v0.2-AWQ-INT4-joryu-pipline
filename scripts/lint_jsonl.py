#!/usr/bin/env python3
"""JSONL 行検証: 空行以外は JSON object であること。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def lint_jsonl_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"{path}: not a file"]
    with path.open(encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{lineno}: invalid JSON: {exc}")
                continue
            if not isinstance(row, dict):
                errors.append(f"{path}:{lineno}: expected JSON object, got {type(row).__name__}")
                continue
            answer = row.get("answer")
            if isinstance(answer, str) and ("<think>" in answer or "</think>" in answer):
                errors.append(f"{path}:{lineno}: answer must not contain '<think>' tags")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        return 0
    errors: list[str] = []
    for arg in args:
        errors.extend(lint_jsonl_file(Path(arg)))
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
