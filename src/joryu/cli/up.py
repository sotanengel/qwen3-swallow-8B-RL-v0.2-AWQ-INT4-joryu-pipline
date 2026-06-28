"""joryu-up: フロント (dashboard) / API / vLLM 常駐デーモン (joryu) を docker compose で起動する。

git 差分から rebuild 対象を自動判定し、必要時は `docker compose build` → `up` を実行する。
未コミット差分に加え、前回起動後の `git pull` 分も rebuild 対象に含める。
joryu ビルド前にホスト空き容量を検査し、不足時は `--force` なしでは中止する。

**既定は dashboard + api + joryu (vLLM 常駐)** — `/jobs` から蒸留ジョブを即投入できる。
`--detach` 時は API / vLLM デーモン / dashboard が ready になるまで待機する。

簡略コマンド:
    uv run joryu-up                     # dashboard + api + joryu (git 差分に応じて build)
    uv run joryu-up --frontend-only     # dashboard のみ
    uv run joryu-up --backend-only      # joryu コンテナのみ
    uv run joryu-up --detach            # バックグラウンド起動 + ready 待ち
    uv run joryu-up --no-wait           # ready 待ちをスキップ
    uv run joryu-up --no-open           # ブラウザ自動起動を無効化
    uv run joryu-up --force             # ディスク不足でも続行
    uv run joryu-up --refresh-stats     # 起動前に joryu-stats を回して dashboard 表示を最新化
    uv run joryu-up --build             # up 対象を強制 rebuild

config.yaml で ``mcp.enabled: true`` のとき、``joryu-up`` は ``mcp`` コンテナ
(``joryu-mcp --http``) も compose up 対象に含める。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from joryu.browser import open_dashboard_when_ready, schedule_open_dashboard
from joryu.compose import (
    compose_down_command,
    compose_up_command,
    image_prune_command,
    run,
    run_build_artifact_cleanup,
    run_builder_cache_cleanup,
    run_pre_browser_image_cleanup,
    run_up_startup_cleanup,
    staged_build_commands,
    vllm_base_build_command,
)
from joryu.docker_delegate import stop_orphan_joryu_containers
from joryu.preflight import (
    PreflightError,
    changed_services_from_git,
    check_disk_space,
    ensure_curation,
    ensure_dashboard_data_paths,
    ensure_prompt_bank,
    ensure_stats_json,
    ensure_vllm_limits,
    git_head_at,
    is_first_up_run,
    needs_vllm_base_build,
    resolve_up_services,
    save_up_state,
    services_to_build,
    should_force_recreate,
    stop_joryu_for_up,
)
from joryu.readiness import wait_for_up_services

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-up",
        description=(
            "git 差分に応じて docker compose build/up する (既定: dashboard + api + joryu)。"
        ),
    )
    g = p.add_mutually_exclusive_group()
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
        "--build",
        action="store_true",
        help="up 対象サービスを git 差分に関係なく強制 rebuild",
    )
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
    p.add_argument(
        "--no-wait",
        action="store_true",
        help="compose up 後の API / vLLM / dashboard ready 待ちをスキップ",
    )
    p.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        metavar="NAME",
        help="compose profile (既定: distill)。複数指定可。",
    )
    return p


def _should_open_browser(args: argparse.Namespace, up_services: list[str]) -> bool:
    return not args.no_open and "dashboard" in up_services


def main(argv: list[str] | None = None) -> int:
    from joryu.logging_config import setup_logging

    setup_logging()
    args = build_parser().parse_args(argv)
    logger.info("[joryu-up] removing dangling images (<none>) before startup")
    run_up_startup_cleanup()

    repo_root = Path.cwd()

    changed = changed_services_from_git(repo_root)
    up_services = resolve_up_services(args, changed, repo_root=repo_root)
    first_run = is_first_up_run(repo_root)
    build_services = services_to_build(
        up_services,
        changed,
        no_build=args.no_build,
        force_build=args.build,
        first_run=first_run,
        repo_root=repo_root,
    )
    build_vllm_base = needs_vllm_base_build(
        repo_root,
        build_services,
        first_run=first_run,
        force_build=args.build,
    )

    try:
        check_disk_space(
            build_services,
            repo_root,
            force=args.force,
            include_vllm_base=build_vllm_base,
        )
    except PreflightError as exc:
        # 容量が足りなくても build 対象がある時は、まず dangling image / 旧 build cache を
        # 自動で回収して再チェックする (joryu-up が世代毎に積み上げた中間層が主因のため)。
        if build_services and not args.force:
            logger.warning("[joryu-up] 容量不足のため `docker builder prune` を試行します")
            run_builder_cache_cleanup()
            try:
                check_disk_space(
                    build_services,
                    repo_root,
                    force=args.force,
                    include_vllm_base=build_vllm_base,
                )
            except PreflightError as exc2:
                logger.error("%s", exc2)
                return 1
        else:
            logger.error("%s", exc)
            return 1

    if "dashboard" in up_services:
        ensure_dashboard_data_paths(repo_root)

    rc = ensure_stats_json(repo_root, force=args.refresh_stats)
    if rc is not None and rc != 0:
        logger.error("[joryu-up] joryu-stats failed, aborting compose up")
        return rc

    if "api" in up_services or "joryu" in up_services:
        try:
            ensure_prompt_bank(repo_root)
        except PreflightError as exc:
            logger.error("%s", exc)
            return 1

    if "joryu" in up_services:
        stop_joryu_for_up()

    rc = ensure_curation(repo_root, up_services)
    if rc is not None and rc != 0:
        logger.error("[joryu-up] joryu-curate failed, aborting compose up")
        return rc

    if build_services:
        compose_profiles = ["always", *(args.profiles or ["distill"])]
        if build_vllm_base:
            logger.info(
                "[joryu-up] building joryu-vllm-base (torch + vLLM compile). "
                "進捗は --progress=plain で stdout に流れます (時間が掛かる場合は "
                "`bash scripts/build-vllm-base.sh` 単体でビルドし "
                "`data/logs/build-vllm-base-<UTC>.log` を確認してください)",
            )
            rc = run(vllm_base_build_command(repo_root=str(repo_root)))
            if rc != 0:
                return rc
        for build_cmd in staged_build_commands(
            build_services,
            profiles=compose_profiles,
        ):
            rc = run(build_cmd)
            if rc != 0:
                return rc
        # 旧ビルドの dangling image / 中間キャッシュ層を即時回収。
        run_build_artifact_cleanup()

    if "api" in up_services or "joryu" in up_services:
        stop_orphan_joryu_containers()
        try:
            ensure_vllm_limits(
                repo_root,
                up_services=up_services,
                joryu_built="joryu" in build_services,
            )
        except PreflightError as exc:
            logger.error("%s", exc)
            return 1

    cmd = compose_up_command(
        services=up_services,
        detach=args.detach,
        build=False,
        force_recreate=should_force_recreate(
            up_services,
            changed,
            build_services,
            first_run=first_run,
        ),
        profiles=["always", *(args.profiles or ["distill"])],
    )
    open_browser = _should_open_browser(args, up_services)
    pre_browser_cleanup = run_pre_browser_image_cleanup if build_services else None
    if open_browser and not args.detach:
        schedule_open_dashboard(pre_open_fn=pre_browser_cleanup)
    # フォアグラウンドのまま compose up に入ると docker がログをストリームし続け、
    # Ctrl-C するまで joryu-up が返らない。これは docker compose 仕様だが、
    # 「joryu-up が帰ってこない」と誤解されやすいので意図を明示する。
    if args.detach:
        logger.info("[joryu-up] starting `docker compose up --detach`")
    else:
        logger.info(
            "[joryu-up] starting `docker compose up` in foreground "
            "(Ctrl-C to stop; pass --detach to background instead)",
        )
    rc = run(cmd)
    if rc != 0:
        logger.error("[joryu-up] compose up failed (exit %s); running rollback", rc)
        rollback_rc = run(compose_down_command(volumes=False))
        if rollback_rc != 0:
            logger.error("[joryu-up] compose down rollback failed (exit %s)", rollback_rc)
        return rc
    if build_services and not open_browser:
        # compose up --force-recreate 後、旧コンテナ参照が外れた dangling image を回収。
        run(image_prune_command())
    head = git_head_at(repo_root)
    if head:
        save_up_state(
            repo_root,
            head,
            built_services=build_services if build_services else None,
        )

    if not args.no_wait and args.detach:
        if not wait_for_up_services(up_services):
            return 1

    if "joryu" in up_services:
        from joryu.orchestrator.factory import build_orchestrator

        build_orchestrator(repo_root).init_distill_active()

    if open_browser and args.detach:
        open_dashboard_when_ready(pre_open_fn=pre_browser_cleanup)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
