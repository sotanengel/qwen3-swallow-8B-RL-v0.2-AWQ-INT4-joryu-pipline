"""joryu-up: フロント (dashboard) とバックエンド (joryu) を docker compose で起動する。

**既定は dashboard + api を起動する** — `/jobs` から蒸留ジョブを投入できる。
joryu コンテナ (vLLM + CUDA, 20GB+) は `--full` か `--backend-only` のときだけビルドする。

簡略コマンド:
    uv run joryu-up                     # dashboard + api (http://localhost:3000, :8000)
    uv run joryu-up --frontend-only     # dashboard のみ
    uv run joryu-up --full              # joryu + dashboard + api を build して起動
    uv run joryu-up --backend-only      # joryu コンテナのみ (蒸留 image を idle 待機)
    uv run joryu-up --detach            # バックグラウンド起動
    uv run joryu-up --refresh-stats     # 起動前に joryu-stats を回して dashboard 表示を最新化

蒸留ジョブは `joryu-up --backend-only` 後に
`docker compose run --rm joryu joryu-distill --no-docker --count 1` で投げる、
あるいは Windows ホストから `uv run joryu-distill` (Docker 自動委譲) で実行する。
"""

from __future__ import annotations

import argparse
import sys

from joryu.cli import stats as cli_stats
from joryu.compose import compose_up_command, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-up",
        description=(
            "フロント + API + バックエンドを docker compose で起動する (既定: dashboard + api)。"
        ),
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--full",
        action="store_true",
        help="joryu + dashboard を両方起動 (vLLM image は ~20GB 必要)",
    )
    g.add_argument(
        "--frontend-only",
        action="store_true",
        help="dashboard のみ (既定と同じ、明示用)",
    )
    g.add_argument(
        "--backend-only",
        action="store_true",
        help="joryu コンテナのみ起動 (蒸留ジョブを `docker compose run` で投げる前段)",
    )
    p.add_argument("--detach", "-d", action="store_true", help="バックグラウンド起動 (-d)")
    p.add_argument("--no-build", action="store_true", help="既存イメージを再利用")
    p.add_argument(
        "--refresh-stats",
        action="store_true",
        help="起動前に joryu-stats を実行して dashboard/public/stats.json を最新化",
    )
    return p


def _services(args: argparse.Namespace) -> list[str] | None:
    if args.full:
        return None  # 全サービス (joryu + dashboard + api)
    if args.backend_only:
        return ["joryu"]
    if args.frontend_only:
        return ["dashboard"]
    # 既定: dashboard + api (/jobs 画面から蒸留ジョブ投入可能)
    return ["dashboard", "api"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.refresh_stats:
        rc = cli_stats.main([])
        if rc != 0:
            print("[joryu-up] joryu-stats failed, aborting compose up", file=sys.stderr)
            return rc

    cmd = compose_up_command(
        services=_services(args),
        detach=args.detach,
        build=not args.no_build,
    )
    return run(cmd)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
