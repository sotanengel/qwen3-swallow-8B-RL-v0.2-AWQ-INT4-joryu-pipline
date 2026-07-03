"""duration 文字列 (`2h`, `30m`, `1h30m` など) のパース (#409 で cli.distill から移設)。"""

from __future__ import annotations

import re

_DURATION_RE = re.compile(r"(\d+)\s*(h|m|s)")


def parse_duration(text: str | None) -> int | None:
    """`2h`, `30m`, `45s`, `1h30m` などを秒数に変換。空/None は None。"""
    if not text:
        return None
    total = 0
    found = False
    for match in _DURATION_RE.finditer(text):
        found = True
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        else:
            total += value
    if not found:
        raise ValueError(f"could not parse duration: {text!r}")
    return total
