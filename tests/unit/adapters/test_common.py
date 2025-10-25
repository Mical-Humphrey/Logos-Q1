from __future__ import annotations

import pytest

from logos.adapters.common import (
    IdempotentCache,
    OrderConflictError,
    RateLimitExceeded,
    RateLimiter,
    RetryConfig,
    RetryableError,
    retry,
)


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


def test_rate_limiter_enforces_sliding_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_calls=2, period=1.0, time_fn=clock.now)

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()

    clock.advance(1.01)
    limiter.acquire()  # should succeed after window advances


def test_retry_retries_retryable_errors() -> None:
    attempts = {"count": 0}

    def flaky_operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableError("transient failure")
        return "ok"

    result = retry(
        flaky_operation,
        retry_config=RetryConfig(
            max_attempts=3, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0
        ),
        classify=lambda exc: exc,
        sleeper=lambda _: None,
    )
    assert result == "ok"
    assert attempts["count"] == 3


def test_idempotent_cache_returns_existing_response() -> None:
    cache = IdempotentCache()

    def resolver() -> dict[str, object]:
        return {"id": 1}

    first = cache.remember("cid-1", {"foo": "bar"}, resolver)
    second = cache.remember("cid-1", {"foo": "bar"}, resolver)
    assert first == second


def test_idempotent_cache_rejects_conflicting_payload() -> None:
    cache = IdempotentCache()
    cache.remember("cid-1", {"foo": 1}, lambda: {"id": 1})
    with pytest.raises(OrderConflictError):
        cache.remember("cid-1", {"foo": 2}, lambda: {"id": 2})
