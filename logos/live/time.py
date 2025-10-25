"""Clock utilities for live trading components.

A dedicated time provider makes it easy to inject deterministic clocks
inside tests while keeping production code on real system time. Future
phases can extend this with NTP sync or exchange clock probes.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Protocol


class TimeProvider(Protocol):
    """Protocol for objects that can supply timestamps."""

    def utc_now(self) -> _dt.datetime:
        """Return the current UTC timestamp."""


@dataclass
class SystemTimeProvider:
    """Default implementation backed by :mod:`datetime`."""

    def utc_now(self) -> _dt.datetime:
        return _dt.datetime.now(tz=_dt.timezone.utc)


@dataclass
class MockTimeProvider:
    """Deterministic clock used in tests."""

    current: _dt.datetime

    def utc_now(self) -> _dt.datetime:
        return self.current

    def advance(self, delta: _dt.timedelta) -> None:
        """Move the internal clock forward for the next call."""
        self.current += delta


def interval_to_timedelta(interval: str) -> _dt.timedelta:
    """Convert interval tokens like '1m' or '5m' into :class:`timedelta`."""

    token = (interval or "").strip().lower()
    if not token:
        raise ValueError("interval must be non-empty")
    if token.endswith("ms"):
        value = float(token[:-2])
        return _dt.timedelta(milliseconds=value)
    unit = token[-1]
    try:
        magnitude = float(token[:-1])
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"invalid interval '{interval}'") from exc
    if magnitude <= 0:
        raise ValueError("interval magnitude must be positive")
    if unit == "s":
        return _dt.timedelta(seconds=magnitude)
    if unit == "m":
        return _dt.timedelta(minutes=magnitude)
    if unit == "h":
        return _dt.timedelta(hours=magnitude)
    if unit == "d":
        return _dt.timedelta(days=magnitude)
    raise ValueError(f"unsupported interval unit '{unit}'")
