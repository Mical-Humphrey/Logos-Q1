from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    Optional,
    Tuple,
    TypeVar,
)

__all__ = [
    "AdapterError",
    "RetryableError",
    "FatalAdapterError",
    "RateLimitExceeded",
    "OrderConflictError",
    "RetryConfig",
    "RateLimiter",
    "retry",
    "IdempotentCache",
]


class AdapterError(RuntimeError):
    """Base exception for hardened adapters."""


class RetryableError(AdapterError):
    """Errors that should trigger retry/backoff."""


class FatalAdapterError(AdapterError):
    """Errors that should surface immediately."""


class RateLimitExceeded(RetryableError):
    """Raised when an operation exceeds the configured rate limit."""


class OrderConflictError(FatalAdapterError):
    """Raised when idempotency is violated (different payload for same client id)."""


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 0.5
    backoff: float = 2.0
    jitter: float = 0.1
    max_delay: float = 5.0

    def next_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.backoff**attempt), self.max_delay)
        if self.jitter:
            jitter = random.uniform(-self.jitter, self.jitter) * delay
            return max(delay + jitter, 0.0)
        return delay


class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(
        self,
        max_calls: int,
        period: float,
        *,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        if max_calls <= 0 or period <= 0:
            raise ValueError("RateLimiter requires positive capacity and period")
        self.max_calls = max_calls
        self.period = period
        self._now = time_fn or time.monotonic
        self._events: Deque[float] = deque()

    def acquire(self) -> None:
        now = self._now()
        cutoff = now - self.period
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        if len(self._events) >= self.max_calls:
            raise RateLimitExceeded(
                f"rate limit exceeded: {self.max_calls} calls per {self.period} seconds"
            )
        self._events.append(now)


T = TypeVar("T")
E = TypeVar("E", bound=BaseException)


def retry(
    operation: Callable[[], T],
    *,
    retry_config: RetryConfig,
    classify: Callable[[BaseException], BaseException] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    attempt = 0
    last_error: Optional[BaseException] = None
    while attempt < retry_config.max_attempts:
        try:
            return operation()
        except BaseException as exc:  # noqa: BLE001
            classified = classify(exc) if classify else exc
            if isinstance(classified, FatalAdapterError):
                raise classified
            if not isinstance(classified, RetryableError):
                raise classified
            last_error = classified
            attempt += 1
            if attempt >= retry_config.max_attempts:
                break
            delay = retry_config.next_delay(attempt - 1)
            if delay:
                sleeper(delay)
    assert last_error is not None
    raise last_error


@dataclass
class CacheEntry:
    payload_hash: Tuple[Tuple[str, Any], ...]
    response: Dict[str, Any]


def _normalize_payload(payload: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    return tuple(sorted(payload.items()))


class IdempotentCache:
    """Remember order payloads keyed by client IDs."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}

    def remember(
        self,
        client_id: str,
        payload: Dict[str, Any],
        resolver: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = _normalize_payload(payload)
        if client_id in self._store:
            entry = self._store[client_id]
            if entry.payload_hash != normalized:
                raise OrderConflictError(
                    f"client_id {client_id} reused with different payload"
                )
            return entry.response
        response = resolver()
        self._store[client_id] = CacheEntry(payload_hash=normalized, response=response)
        return response

    def get(self, client_id: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(client_id)
        return dict(entry.response) if entry else None

    def update(self, client_id: str, response: Dict[str, Any]) -> None:
        if client_id not in self._store:
            self._store[client_id] = CacheEntry(payload_hash=tuple(), response=response)
        else:
            self._store[client_id].response = response

    def keys(self) -> Iterable[str]:
        return list(self._store.keys())
