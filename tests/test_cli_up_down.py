"""cli/up.py と cli/down.py: 引数パースと main() の dispatch。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from joryu.cli import down as cli_down
from joryu.cli import up as cli_up
from joryu.orchestrator.state import OrchestratorState, OrchestratorStatus

_UP_WITH_DISTILL = ["docker", "compose", "--profile", "always", "--profile", "distill", "up"]
_BUILD_PREFIX = ["docker", "compose", "--profile", "always", "--profile", "distill", "build"]


def _compose_build(*services: str) -> list[str]:
    return [*_BUILD_PREFIX, *services]


def _vllm_base_build(repo_root: str) -> list[str]:
    return [
        "docker",
        "build",
        "--progress=plain",
        "-f",
        "Dockerfile.vllm-base",
        "-t",
        "joryu-vllm-base:latest",
        repo_root,
    ]


def _compose_up_cmd(*services: str, detach: bool = False, force_recreate: bool = True) -> list[str]:
    cmd = list(_UP_WITH_DISTILL)
    if force_recreate:
        cmd.append("--force-recreate")
    if detach:
        cmd.append("-d")
    cmd.extend(services)
    return cmd


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rc: int = 0,
) -> list[list[str]]:
    """docker subprocess.run をキャプチャし、副作用なしに固定 rc を返すフェイク。"""
    calls: list[list[str]] = []

    class _Done:
        def __init__(self, *, stdout: str = "", returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout

    def _fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> _Done:
        is_git_capture = kwargs.get("capture_output") and cmd and cmd[0] == "git"
        if not is_git_capture:
            calls.append(cmd)
        if kwargs.get("capture_output"):
            if len(cmd) >= 3 and cmd[0:3] == ["git", "rev-parse", "HEAD"]:
                return _Done(stdout="test-head\n")
            if len(cmd) >= 4 and cmd[0:4] == ["docker", "image", "inspect"]:
                return _Done(returncode=0)
            return _Done()
        return _Done()

    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    monkeypatch.setattr("joryu.cli.up.schedule_open_dashboard", lambda **_: None)
    monkeypatch.setattr("joryu.cli.up.open_dashboard_when_ready", lambda **_: None)
    monkeypatch.setattr("joryu.cli.up.wait_for_up_services", lambda _services: True)
    monkeypatch.setattr("joryu.preflight.should_up_mcp", lambda _root: False)
    monkeypatch.setattr("joryu.cli.up.is_first_up_run", lambda _root: False)
    # 空き容量チェックは環境依存なので既定で no-op 化 (insufficient disk テストでは上書き)
    monkeypatch.setattr("joryu.cli.up.check_disk_space", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.ensure_prompt_bank", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.ensure_stats_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.ensure_curation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.ensure_vllm_limits", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.stop_orphan_joryu_containers", lambda **_kwargs: None)
    monkeypatch.setattr("joryu.cli.up.stop_joryu_for_up", lambda **_kwargs: None)
    monkeypatch.setattr("joryu.preflight.services_missing_build_at_head", lambda *_a, **_k: set())
    monkeypatch.setattr("joryu.preflight.git_head_at", lambda *_a, **_k: "test-head")
    monkeypatch.setattr("joryu.cli.up.save_up_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("joryu.preflight.docker_image_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("joryu.cli.up.needs_vllm_base_build", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        "joryu.orchestrator.factory.build_orchestrator",
        lambda *_args, **_kwargs: type(
            "Orch",
            (),
            {
                "init_distill_active": lambda self: None,
                "get_state": lambda self: OrchestratorState(status=OrchestratorStatus.STOPPED),
            },
        )(),
    )
    return calls


_STARTUP_IMAGE_PRUNE = ["docker", "image", "prune", "-f"]


def test_up_skips_init_distill_when_profile_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    """STARTING/SWITCHING 中は joryu-up が FSM を distill active で上書きしない。"""
    init_calls: list[str] = []

    class _Orch:
        def get_state(self) -> OrchestratorState:
            return OrchestratorState(
                status=OrchestratorStatus.STARTING,
                target=None,
            )

        def init_distill_active(self) -> None:
            init_calls.append("called")

    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr(
        "joryu.orchestrator.factory.build_orchestrator",
        lambda *_args, **_kwargs: _Orch(),
    )
    rc = cli_up.main([])
    assert rc == 0
    assert init_calls == []


def test_up_prunes_dangling_images_at_startup_without_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rebuild なしでも起動直後に dangling image を回収する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main([])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard", "api", "joryu"]


def test_up_default_no_changes_builds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """git 差分なし・初回でもない・joryu イメージあり → build なし、dashboard + api up。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main([])
    assert rc == 0
    assert len(calls) == 2
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard", "api", "joryu"]


def test_up_stops_joryu_before_compose_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """joryu を up する既定フローでは compose up 前に既存 joryu を停止する。"""
    calls = _patch_runner(monkeypatch)
    order: list[str] = []
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr(
        "joryu.cli.up.stop_joryu_for_up",
        lambda **_: order.append("stop_joryu"),
    )

    rc = cli_up.main([])
    assert rc == 0
    assert order == ["stop_joryu"]
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1][0:7] == _UP_WITH_DISTILL


def test_up_frontend_only_does_not_stop_joryu(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_calls: list[str] = []
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})
    monkeypatch.setattr(
        "joryu.cli.up.stop_joryu_for_up",
        lambda **_: stop_calls.append("stop"),
    )
    rc = cli_up.main(["--frontend-only"])
    assert rc == 0
    assert stop_calls == []
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard"]


def test_up_joryu_diff_triggers_build_then_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """api 側 git 差分 → build api → up dashboard + api。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"api"})
    rc = cli_up.main([])
    assert rc == 0
    assert len(calls) == 5
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_build("api")
    assert calls[2] == ["docker", "image", "prune", "-f"]
    assert calls[3] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[4] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_default_brings_up_all_builds_only_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既定 → 全サービス up、差分がある dashboard のみ build。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"dashboard"})
    rc = cli_up.main([])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_build("dashboard")
    assert calls[2] == ["docker", "image", "prune", "-f"]
    assert calls[3] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[4] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_frontend_only_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})
    rc = cli_up.main(["--frontend-only"])
    assert rc == 0
    assert len(calls) == 2
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard"]


def test_up_backend_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """--backend-only は joryu 常駐コンテナだけ up。joryu は image: 直参照なので build しない。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})
    rc = cli_up.main(["--backend-only", "--detach"])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_up_cmd("joryu", detach=True, force_recreate=False)


def test_up_rejects_removed_full_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    with pytest.raises(SystemExit):
        cli_up.main(["--full"])


def test_up_mutex_flags_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    with pytest.raises(SystemExit):
        cli_up.main(["--frontend-only", "--backend-only"])


def test_up_refresh_stats_before_compose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _patch_runner(monkeypatch)
    stats_calls: list[bool] = []
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())

    def _fake_ensure_stats(_root: object, *, force: bool = False, log=None) -> int | None:
        stats_calls.append(force)
        return 0

    monkeypatch.setattr("joryu.cli.up.ensure_stats_json", _fake_ensure_stats)
    monkeypatch.chdir(tmp_path)
    rc = cli_up.main(["--refresh-stats", "--frontend-only"])
    assert rc == 0
    assert stats_calls == [True]
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard"]


def test_up_aborts_when_curation_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())

    def _fail_curation(_root: object, _services: list[str]) -> int:
        return 1

    monkeypatch.setattr("joryu.cli.up.ensure_curation", _fail_curation)
    monkeypatch.chdir(tmp_path)
    rc = cli_up.main(["--frontend-only"])
    assert rc == 1
    assert calls == [_STARTUP_IMAGE_PRUNE]


def test_up_no_build_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr(
        "joryu.cli.up.changed_services_from_git",
        lambda _root: {"dashboard"},
    )
    cli_up.main(["--no-build"])
    assert len(calls) == 2
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard", "api", "joryu"]


def test_up_no_build_flag_force_recreate_when_joryu_runtime_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--no-build でも api/joryu ランタイム差分時は api コンテナを再作成する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr(
        "joryu.cli.up.changed_services_from_git",
        lambda _root: {"joryu"},
    )
    cli_up.main(["--no-build"])
    assert len(calls) == 2
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_build_flag_forces_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main(["--build"])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    # joryu / joryu-seed は image: 直参照になったため build 対象から外れる。
    # heavy = joryu-job, joryu-judge / light = dashboard, api。
    assert calls[1] == _compose_build("joryu-job")
    assert calls[2] == _compose_build("joryu-judge")
    assert calls[3] == _compose_build("dashboard", "api")
    assert calls[4] == ["docker", "image", "prune", "-f"]
    assert calls[5] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[6] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_builds_vllm_base_before_joryu_on_first_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.is_first_up_run", lambda _root: True)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr("joryu.cli.up.needs_vllm_base_build", lambda *_args, **_kwargs: True)
    monkeypatch.chdir(tmp_path)
    rc = cli_up.main([])
    assert rc == 0
    assert calls[1] == _vllm_base_build(str(tmp_path))
    assert calls[2] == _compose_build("joryu-job")


def test_up_first_run_builds_up_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.is_first_up_run", lambda _root: True)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main([])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_build("joryu-job")
    assert calls[2] == _compose_build("joryu-judge")
    assert calls[3] == _compose_build("dashboard", "api")
    assert calls[-1] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_builds_joryu_when_image_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """joryu-job:latest が無い (api job 実行不可) なら build 対象に積む。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr("joryu.preflight.docker_image_exists", lambda *_args, **_kwargs: False)
    rc = cli_up.main([])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_build("joryu-job")
    assert calls[2] == ["docker", "image", "prune", "-f"]
    assert calls[3] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[4] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_prunes_dangling_images_after_successful_up_with_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build 後 --detach では ready 待ちの後・ブラウザ起動直前に `<none>` を回収する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"api"})

    def _open_when_ready(**kwargs: object) -> None:
        pre_open_fn = kwargs.get("pre_open_fn")
        if callable(pre_open_fn):
            pre_open_fn()

    monkeypatch.setattr("joryu.cli.up.open_dashboard_when_ready", _open_when_ready)
    rc = cli_up.main(["--detach"])
    assert rc == 0
    assert calls[-1] == ["docker", "image", "prune", "-f"]
    assert calls.count(["docker", "image", "prune", "-f"]) == 3


def test_up_aborts_on_insufficient_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """空き容量不足が prune 後も解消しない時は abort する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})

    def _fail_disk(
        services: list[str],
        repo_root: object,
        *,
        force: bool,
        include_vllm_base: bool = False,
        disk_usage_fn: object = None,
    ) -> None:
        from joryu.preflight import PreflightError

        raise PreflightError("disk full")

    monkeypatch.setattr("joryu.cli.up.check_disk_space", _fail_disk)
    rc = cli_up.main([])
    assert rc == 1
    # 起動時 image prune の後、容量不足時は builder prune のみ試行する
    assert calls == [
        _STARTUP_IMAGE_PRUNE,
        ["docker", "builder", "prune", "-a", "-f"],
    ]


def test_up_auto_prunes_and_continues_when_disk_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 回目の disk check 失敗 → builder prune → 2 回目成功なら build/up を続行する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})

    attempts: list[int] = []

    def _flaky_disk(
        services: list[str],
        repo_root: object,
        *,
        force: bool,
        include_vllm_base: bool = False,
        disk_usage_fn: object = None,
    ) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            from joryu.preflight import PreflightError

            raise PreflightError("disk tight, retry after prune")

    monkeypatch.setattr("joryu.cli.up.check_disk_space", _flaky_disk)
    rc = cli_up.main([])
    assert rc == 0
    assert len(attempts) == 2
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[2] == _compose_build("joryu-job")
    assert calls[3] == ["docker", "image", "prune", "-f"]
    assert calls[4] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[5][:7] == _UP_WITH_DISTILL


def test_up_force_bypasses_disk_check(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})
    recorded: list[bool] = []

    def _record_force(
        services: list[str],
        repo_root: object,
        *,
        force: bool,
        include_vllm_base: bool = False,
    ) -> None:
        recorded.append(force)

    monkeypatch.setattr("joryu.cli.up.check_disk_space", _record_force)
    rc = cli_up.main(["--force"])
    assert rc == 0
    assert recorded == [True]
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == _compose_build("joryu-job")
    assert calls[2] == ["docker", "image", "prune", "-f"]
    assert calls[3] == ["docker", "builder", "prune", "-a", "-f"]
    assert calls[4] == _compose_up_cmd("dashboard", "api", "joryu")


def test_up_detach_waits_for_services(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    waited: list[list[str]] = []
    monkeypatch.setattr(
        "joryu.cli.up.wait_for_up_services",
        lambda services: waited.append(list(services)) or True,
    )
    rc = cli_up.main(["--detach"])
    assert rc == 0
    assert waited == [["dashboard", "api", "joryu"]]


def test_up_detach_fails_when_wait_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr("joryu.cli.up.wait_for_up_services", lambda _services: False)
    rc = cli_up.main(["--detach"])
    assert rc == 1


def test_up_detach_opens_browser_after_dashboard_up(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    opened: list[bool] = []
    monkeypatch.setattr(
        "joryu.cli.up.open_dashboard_when_ready",
        lambda **_: opened.append(True),
    )
    rc = cli_up.main(["--detach"])
    assert rc == 0
    assert calls[-1] == [*_UP_WITH_DISTILL, "-d", "dashboard", "api", "joryu"]
    assert opened == [True]


def test_up_detach_prunes_dangling_images_before_browser_after_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build 後 --detach では ready 待ちの後・ブラウザ起動直前に dangling image を回収する。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"api"})
    browser_kwargs: list[dict[str, object]] = []

    def _open_when_ready(**kwargs: object) -> None:
        browser_kwargs.append(dict(kwargs))

    monkeypatch.setattr("joryu.cli.up.open_dashboard_when_ready", _open_when_ready)
    rc = cli_up.main(["--detach"])
    assert rc == 0
    assert calls[4] == _compose_up_cmd("dashboard", "api", "joryu", detach=True)
    assert len(calls) == 5
    assert browser_kwargs == [{"pre_open_fn": cli_up.run_pre_browser_image_cleanup}]


def test_up_backend_only_does_not_open_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu-job"})
    opened: list[bool] = []
    monkeypatch.setattr(
        "joryu.cli.up.open_dashboard_when_ready",
        lambda **_: opened.append(True),
    )
    cli_up.main(["--backend-only", "--detach"])
    assert opened == []


def test_up_no_open_skips_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    opened: list[bool] = []
    monkeypatch.setattr(
        "joryu.cli.up.open_dashboard_when_ready",
        lambda **_: opened.append(True),
    )
    cli_up.main(["--detach", "--no-open"])
    assert opened == []


def test_up_foreground_schedules_browser_before_compose(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    order: list[str] = []

    def _schedule(**_: object) -> None:
        order.append("schedule")

    def _fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        is_git_capture = kwargs.get("capture_output") and cmd and cmd[0] == "git"
        if not is_git_capture:
            calls.append(cmd)
            order.append("compose")

        class _Done:
            returncode = 0
            stdout = "test-head\n" if is_git_capture else ""

        return _Done()

    monkeypatch.setattr("joryu.cli.up.schedule_open_dashboard", _schedule)
    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    cli_up.main([])
    assert order == ["compose", "schedule", "compose"]


def test_up_foreground_passes_pre_browser_cleanup_after_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"api"})
    browser_kwargs: list[dict[str, object]] = []

    def _schedule(**kwargs: object) -> None:
        browser_kwargs.append(dict(kwargs))

    monkeypatch.setattr("joryu.cli.up.schedule_open_dashboard", _schedule)
    rc = cli_up.main([])
    assert rc == 0
    assert browser_kwargs == [{"pre_open_fn": cli_up.run_pre_browser_image_cleanup}]


def test_up_aborts_when_prompt_bank_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())

    def _fail_prompt_bank(_root: object) -> None:
        from joryu.preflight import PreflightError

        raise PreflightError("prompt bank missing")

    monkeypatch.setattr("joryu.cli.up.ensure_prompt_bank", _fail_prompt_bank)
    rc = cli_up.main([])
    assert rc == 1
    assert calls == [_STARTUP_IMAGE_PRUNE]


def test_up_frontend_only_skips_prompt_bank(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    prompt_calls: list[object] = []
    monkeypatch.setattr(
        "joryu.cli.up.ensure_prompt_bank",
        lambda repo_root: prompt_calls.append(repo_root),
    )
    rc = cli_up.main(["--frontend-only"])
    assert rc == 0
    assert prompt_calls == []
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard"]


def test_down_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    rc = cli_down.main([])
    assert rc == 0
    assert calls[0][:3] == ["docker", "compose", "--profile"]
    assert "down" in calls[0]


def test_down_with_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    rc = cli_down.main(["--volumes"])
    assert rc == 0
    assert "-v" in calls[0] or "--volumes" in calls[0]


def test_serve_alias_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """joryu-serve は joryu-up --frontend-only と等価。"""
    from joryu.cli import serve as cli_serve

    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_serve.main([])
    assert rc == 0
    assert calls[0] == _STARTUP_IMAGE_PRUNE
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard"]


def test_up_compose_failure_runs_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)

    class _FailUp:
        returncode = 1

    def _fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("capture_output"):
            return type("R", (), {"returncode": 0, "stdout": "test-head\n"})()
        calls.append(cmd)
        if len(cmd) >= 7 and cmd[0:7] == _UP_WITH_DISTILL:
            return _FailUp()
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr("joryu.preflight.joryu_container_running", lambda **_: False)
    rc = cli_up.main(["--detach"])
    assert rc == 1
    assert any(cmd[0:3] == ["docker", "compose", "--profile"] and "down" in cmd for cmd in calls)


def test_up_includes_mcp_when_config_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    monkeypatch.setattr("joryu.preflight.should_up_mcp", lambda _root: True)
    rc = cli_up.main([])
    assert rc == 0
    assert calls[1] == [*_UP_WITH_DISTILL, "dashboard", "mcp", "api", "joryu"]
