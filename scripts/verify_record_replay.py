#!/usr/bin/env python3
"""JSONL レコードの tools フィールドから chat_template 入力を再構築できることを検証。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from joryu.record_replay import rebuild_chat_template_inputs


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: verify_record_replay.py <responses.jsonl>", file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    found_with_tools = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        tools = record.get("tools") or []
        if not tools:
            continue
        found_with_tools = True
        rebuild_chat_template_inputs(record)
    if not found_with_tools:
        print("[verify_record_replay] no records with tools; skipping", file=sys.stderr)
    else:
        print("[verify_record_replay] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
