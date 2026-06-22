"""cli/up.py と cli/down.py: 引数パースと main() の dispatch。"""

from __future__ import annotations

from typing import Any

import pytest

from joryu.cli import down as cli_down
from joryu.cli import up as cli_up


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rc: int = 0,
) -> list[list[str]]:
    """docker subprocess.run をキャプチャし、副作用なしに固定 rc を返すフェイク。"""
    calls: list[list[str]] = []

    class _Done:
        def __init__(self) -> None:
            self.returncode = rc

    def _fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> _Done:
        calls.append(cmd)
        return _Done()

    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    monkeypatch.setattr("joryu.cli.up.schedule_open_dashboard", lambda **_: None)
    monkeypatch.setattr("joryu.cli.up.open_dashboard_when_ready", lambda **_: None)
    monkeypatch.setattr("joryu.cli.up.is_first_up_run", lambda _root: False)
    monkeypatch.setattr("joryu.cli.up.git_head_at", lambda _root: "abc")
    monkeypatch.setattr("joryu.cli.up.save_up_state", lambda *_args: None)
    # 空き容量チェックは環境依存なので既定で no-op 化 (insufficient disk テストでは上書き)
    monkeypatch.setattr("joryu.cli.up.check_disk_space", lambda *_args, **_kwargs: None)
    return calls


def test_up_default_no_changes_builds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """git 差分なし・初回でもない → build なし、dashboard + api up。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main([])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0] == ["docker", "compose", "up", "dashboard", "api"]


def test_up_joryu_diff_triggers_build_then_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """api 側 git 差分 → build api → up dashboard + api。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"api"})
    rc = cli_up.main([])
    assert rc == 0
    assert len(calls) == 2
    assert calls[0] == ["docker", "compose", "build", "api"]
    assert calls[1] == ["docker", "compose", "up", "dashboard", "api"]


def test_up_full_brings_up_all_builds_only_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--full → 全サービス up、差分がある dashboard のみ build。"""
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"dashboard"})
    rc = cli_up.main(["--full"])
    assert rc == 0
    assert calls[0] == ["docker", "compose", "build", "dashboard"]
    assert calls[1] == ["docker", "compose", "up", "dashboard", "api", "joryu"]


def test_up_frontend_only_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu"})
    rc = cli_up.main(["--frontend-only"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0] == ["docker", "compose", "up", "dashboard"]


def test_up_backend_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu"})
    rc = cli_up.main(["--backend-only", "--detach"])
    assert rc == 0
    assert calls[0] == ["docker", "compose", "build", "joryu"]
    assert calls[1] == ["docker", "compose", "up", "-d", "joryu"]


def test_up_mutex_flags_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    with pytest.raises(SystemExit):
        cli_up.main(["--frontend-only", "--backend-only"])


def test_up_full_and_frontend_only_mutex(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    with pytest.raises(SystemExit):
        cli_up.main(["--full", "--frontend-only"])


def test_up_refresh_stats_runs_before_compose(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    stats_calls: list[list[str] | None] = []
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())

    def _fake_stats_main(argv: list[str] | None = None) -> int:
        stats_calls.append(argv)
        return 0

    monkeypatch.setattr("joryu.cli.stats.main", _fake_stats_main)
    rc = cli_up.main(["--refresh-stats", "--frontend-only"])
    assert rc == 0
    assert stats_calls == [[]]
    assert calls[0] == ["docker", "compose", "up", "dashboard"]


def test_up_no_build_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr(
        "joryu.cli.up.changed_services_from_git",
        lambda _root: {"dashboard", "joryu"},
    )
    cli_up.main(["--no-build", "--full"])
    assert len(calls) == 1
    assert calls[0] == ["docker", "compose", "up", "dashboard", "api", "joryu"]


def test_up_build_flag_forces_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main(["--build"])
    assert rc == 0
    assert calls[0] == ["docker", "compose", "build", "dashboard", "api", "joryu"]
    assert calls[1] == ["docker", "compose", "up", "dashboard", "api"]


def test_up_first_run_builds_up_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.is_first_up_run", lambda _root: True)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: set())
    rc = cli_up.main([])
    assert rc == 0
    assert calls[0] == ["docker", "compose", "build", "dashboard", "api"]


def test_up_aborts_on_insufficient_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu"})

    def _fail_disk(
        services: list[str],
        repo_root: object,
        *,
        force: bool,
        disk_usage_fn: object = None,
    ) -> None:
        from joryu.preflight import PreflightError

        raise PreflightError("disk full")

    monkeypatch.setattr("joryu.cli.up.check_disk_space", _fail_disk)
    rc = cli_up.main([])
    assert rc == 1
    assert calls == []


def test_up_force_bypasses_disk_check(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu"})
    recorded: list[bool] = []

    def _record_force(services: list[str], repo_root: object, *, force: bool) -> None:
        recorded.append(force)

    monkeypatch.setattr("joryu.cli.up.check_disk_space", _record_force)
    rc = cli_up.main(["--force"])
    assert rc == 0
    assert recorded == [True]
    assert calls[0] == ["docker", "compose", "build", "joryu"]
    assert calls[1] == ["docker", "compose", "up", "dashboard", "api"]


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
    assert calls[-1] == ["docker", "compose", "up", "-d", "dashboard", "api"]
    assert opened == [True]


def test_up_backend_only_does_not_open_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch)
    monkeypatch.setattr("joryu.cli.up.changed_services_from_git", lambda _root: {"joryu"})
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
        calls.append(cmd)
        order.append("compose")

        class _Done:
            returncode = 0

        return _Done()

    monkeypatch.setattr("joryu.cli.up.schedule_open_dashboard", _schedule)
    monkeypatch.setattr("joryu.compose.subprocess.run", _fake_run)
    cli_up.main([])
    assert order == ["schedule", "compose"]


def test_down_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    rc = cli_down.main([])
    assert rc == 0
    assert calls[0] == ["docker", "compose", "down"]


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
    assert calls[0] == ["docker", "compose", "up", "dashboard"]
