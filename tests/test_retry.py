"""utils/retry.py のテスト。"""

from __future__ import annotations

import pytest

from joryu.utils.retry import ExponentialBackoff, call_with_retry, retry_on


def test_exponential_backoff_grows_and_caps() -> None:
    policy = ExponentialBackoff(base=1.0, max_delay=4.0, jitter=0.0)
    assert policy.delay_for_attempt(0) == 1.0
    assert policy.delay_for_attempt(1) == 2.0
    assert policy.delay_for_attempt(2) == 4.0
    assert policy.delay_for_attempt(3) == 4.0


def test_exponential_backoff_jitter_within_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("joryu.utils.retry.random.uniform", lambda _a, _b: 0.05)
    policy = ExponentialBackoff(base=1.0, max_delay=8.0, jitter=0.1)
    assert policy.delay_for_attempt(0) == pytest.approx(1.05)


def test_call_with_retry_succeeds_after_transient_failure() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("transient")
        return "ok"

    sleeps: list[float] = []
    result = call_with_retry(
        flaky,
        exceptions=(TimeoutError,),
        attempts=5,
        backoff=ExponentialBackoff(base=0.01, max_delay=0.02, jitter=0.0),
        sleep_fn=sleeps.append,
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_call_with_retry_raises_after_max_attempts() -> None:
    def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        call_with_retry(
            boom,
            exceptions=(RuntimeError,),
            attempts=2,
            backoff=ExponentialBackoff(base=0.01, max_delay=0.01, jitter=0.0),
            sleep_fn=lambda _s: None,
        )


def test_retry_on_decorator_filters_exceptions() -> None:
    calls = {"n": 0}
    fast = ExponentialBackoff(base=0.01, max_delay=0.01, jitter=0.0)

    @retry_on(ValueError, attempts=3, backoff=fast)
    def only_value_error() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("retry me")
        return 42

    assert only_value_error() == 42
    assert calls["n"] == 2

    @retry_on(ValueError, attempts=2)
    def raises_type_error() -> None:
        raise TypeError("no retry")

    with pytest.raises(TypeError):
        raises_type_error()
