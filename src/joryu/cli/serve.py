"""joryu-serve: `joryu-up --frontend-only` の互換エイリアス。"""

from __future__ import annotations

import sys

from joryu.cli.up import main as up_main


def main(argv: list[str] | None = None) -> int:
    forwarded = list(argv) if argv is not None else []
    if "--frontend-only" not in forwarded:
        forwarded.insert(0, "--frontend-only")
    return up_main(forwarded)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
