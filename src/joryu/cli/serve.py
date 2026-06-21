"""joryu-serve: ダッシュボードを docker compose で起動する簡易ラッパ。"""

from __future__ import annotations

import argparse
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-serve",
        description="ダッシュボードを起動 (docker compose up dashboard)。",
    )
    p.add_argument("--detach", action="store_true", help="バックグラウンド起動 (-d)")
    p.add_argument("--no-build", action="store_true", help="既存イメージを再利用")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = ["docker", "compose", "up", "dashboard"]
    if not args.no_build:
        cmd.append("--build")
    if args.detach:
        cmd.append("-d")
    print(f"[joryu-serve] {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
