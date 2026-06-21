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
    return calls


def test_up_default_is_dashboard_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """既定は dashboard のみ起動 (joryu イメージは 20GB+ なので明示時のみビルドする)。"""
    calls = _patch_runner(monkeypatch)
    rc = cli_up.main([])
    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:3] == ["docker", "compose", "up"]
    assert "--build" in cmd
    assert cmd[-1] == "dashboard"
    assert "joryu" not in cmd


def test_up_full_brings_up_all_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """--full で joryu (vLLM) + dashboard を両方起動。"""
    calls = _patch_runner(monkeypatch)
    rc = cli_up.main(["--full"])
    assert rc == 0
    cmd = calls[0]
    assert cmd[:3] == ["docker", "compose", "up"]
    # サービス指定なし = compose 全サービス
    assert "dashboard" not in cmd
    assert "joryu" not in cmd


def test_up_frontend_only_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """--frontend-only は既定と同じ (後方互換のため残す)。"""
    calls = _patch_runner(monkeypatch)
    rc = cli_up.main(["--frontend-only"])
    assert rc == 0
    cmd = calls[0]
    assert cmd[-1] == "dashboard"
    assert "joryu" not in cmd


def test_up_backend_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    rc = cli_up.main(["--backend-only", "--detach"])
    assert rc == 0
    cmd = calls[0]
    assert cmd[-1] == "joryu"
    assert "-d" in cmd


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

    def _fake_stats_main(argv: list[str] | None = None) -> int:
        stats_calls.append(argv)
        return 0

    monkeypatch.setattr("joryu.cli.stats.main", _fake_stats_main)
    rc = cli_up.main(["--refresh-stats", "--frontend-only"])
    assert rc == 0
    assert stats_calls == [[]]
    # その後 compose up dashboard が呼ばれている
    assert calls[0][-1] == "dashboard"


def test_up_no_build_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch)
    cli_up.main(["--no-build"])
    assert "--build" not in calls[0]


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
    rc = cli_serve.main([])
    assert rc == 0
    cmd = calls[0]
    assert cmd[-1] == "dashboard"
    assert cmd[:3] == ["docker", "compose", "up"]
