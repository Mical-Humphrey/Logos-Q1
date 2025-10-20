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
