"""joryu-up: フロント (dashboard) とバックエンド (joryu) を docker compose で起動する。

git 差分から rebuild 対象を自動判定し、必要時は `docker compose build` → `up` を実行する。
joryu ビルド前にホスト空き容量を検査し、不足時は `--force` なしでは中止する。

簡略コマンド:
    uv run joryu-up                     # git 差分に応じて build+up (変更なしなら dashboard up のみ)
    uv run joryu-up --full              # joryu + dashboard を up (差分ある方だけ build)
    uv run joryu-up --backend-only      # joryu コンテナのみ
    uv run joryu-up --detach            # バックグラウンド起動
    uv run joryu-up --no-open           # ブラウザ自動起動を無効化
    uv run joryu-up --force             # ディスク不足でも続行
    uv run joryu-up --refresh-stats     # 起動前に joryu-stats を回して dashboard 表示を最新化
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from joryu.browser import open_dashboard_when_ready, schedule_open_dashboard
from joryu.cli import stats as cli_stats
from joryu.compose import compose_build_command, compose_up_command, run
from joryu.preflight import (
    PreflightError,
    changed_services_from_git,
    check_disk_space,
    resolve_up_services,
    services_to_build,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-up",
        description=(
            "git 差分に応じて docker compose build/up する (変更なしなら dashboard up のみ)。"
        ),
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--full",
        action="store_true",
        help="joryu + dashboard を両方 up (差分があるサービスのみ build)",
    )
    g.add_argument(
        "--frontend-only",
        action="store_true",
        help="dashboard のみ up",
    )
    g.add_argument(
        "--backend-only",
        action="store_true",
        help="joryu コンテナのみ up",
    )
    p.add_argument("--detach", "-d", action="store_true", help="バックグラウンド起動 (-d)")
    p.add_argument("--no-build", action="store_true", help="build をスキップして up のみ")
    p.add_argument(
        "--force",
        action="store_true",
        help="ディスク容量 preflight をスキップして続行",
    )
    p.add_argument(
        "--refresh-stats",
        action="store_true",
        help="起動前に joryu-stats を実行して dashboard/public/stats.json を最新化",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="dashboard 起動後にブラウザを開かない",
    )
    return p


def _should_open_browser(args: argparse.Namespace, up_services: list[str]) -> bool:
    return not args.no_open and "dashboard" in up_services


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd()

    if args.refresh_stats:
        rc = cli_stats.main([])
        if rc != 0:
            print("[joryu-up] joryu-stats failed, aborting compose up", file=sys.stderr)
            return rc

    changed = changed_services_from_git(repo_root)
    up_services = resolve_up_services(args, changed)
    build_services = services_to_build(up_services, changed, no_build=args.no_build)

    try:
        check_disk_space(build_services, repo_root, force=args.force)
    except PreflightError as exc:
        print(exc, file=sys.stderr)
        return 1

    if build_services:
        rc = run(compose_build_command(services=build_services))
        if rc != 0:
            return rc

    cmd = compose_up_command(
        services=up_services,
        detach=args.detach,
        build=False,
    )
    open_browser = _should_open_browser(args, up_services)
    if open_browser and not args.detach:
        schedule_open_dashboard()
    rc = run(cmd)
    if rc == 0 and open_browser and args.detach:
        open_dashboard_when_ready()
    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
