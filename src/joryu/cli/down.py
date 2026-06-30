"""joryu-down: docker compose で起動した joryu / dashboard を停止する。"""

from __future__ import annotations

import argparse
import sys

from joryu.compose import compose_down_command, run
from joryu.orchestrator.profile import ALL_COMPOSE_PROFILES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-down",
        description="フロント + バックエンドを docker compose で停止する。",
    )
    p.add_argument(
        "--volumes",
        "-v",
        action="store_true",
        help=(
            "名前付き volume (例: hf-cache) も削除する (HF ダウンロードキャッシュも消える点に注意)"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = compose_down_command(volumes=args.volumes, profiles=list(ALL_COMPOSE_PROFILES))
    return run(cmd)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
