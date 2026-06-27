"""指数バックオフ + jitter 付きリトライ (stdlib のみ、tenacity 非採用)。"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class ExponentialBackoff:
    """attempt ごとの待機秒数を計算する (0-based attempt)。"""

    def __init__(
        self,
        *,
        base: float = 0.5,
        max_delay: float = 30.0,
        jitter: float = 0.1,
    ) -> None:
        if base <= 0:
            raise ValueError("base must be positive")
        if max_delay <= 0:
            raise ValueError("max_delay must be positive")
        if jitter < 0:
            raise ValueError("jitter must be non-negative")
        self.base = base
        self.max_delay = max_delay
        self.jitter = jitter

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 0:
            raise ValueError("attempt must be non-negative")
        exp = min(self.max_delay, self.base * (2**attempt))
        if self.jitter <= 0:
            return exp
        jitter_range = exp * self.jitter
        return max(0.0, exp + random.uniform(-jitter_range, jitter_range))


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    exceptions: tuple[type[BaseException], ...],
    attempts: int = 3,
    backoff: ExponentialBackoff | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> T:
    """fn を exceptions 発生時に指数バックオフ付きで再試行する。"""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    policy = backoff or ExponentialBackoff()
    pause = sleep_fn or time.sleep
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt == attempts - 1:
                break
            pause(policy.delay_for_attempt(attempt))
    assert last_exc is not None
    raise last_exc


def retry_on(
    *exceptions: type[BaseException],
    attempts: int = 3,
    backoff: ExponentialBackoff | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """指定例外で指数バックオフ + jitter リトライする decorator。"""

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return call_with_retry(
                lambda: fn(*args, **kwargs),
                exceptions=exceptions,
                attempts=attempts,
                backoff=backoff,
                sleep_fn=sleep_fn,
            )

        return wrapper

    return decorator
