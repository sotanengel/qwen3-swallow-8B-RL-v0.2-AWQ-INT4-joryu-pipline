"""hard_deadline のテスト。"""

from __future__ import annotations

import types

import pytest

from joryu.hard_deadline import install_hard_deadline


def test_install_hard_deadline_noop_for_non_positive() -> None:
    install_hard_deadline(0)
    install_hard_deadline(-1)


def test_install_hard_deadline_uses_timer_when_no_sigalrm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fired: list[int] = []

    class _Timer:
        def __init__(self, seconds: float, fn) -> None:
            fired.append(int(seconds))
            self.daemon = False

        def start(self) -> None:
            return None

    monkeypatch.setattr("joryu.hard_deadline.signal", types.SimpleNamespace())
    monkeypatch.setattr("joryu.hard_deadline.threading.Timer", _Timer)
    install_hard_deadline(30)
    assert fired == [30]
