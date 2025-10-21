from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

UTC = ZoneInfo("UTC")


def _coerce_zone(zone: ZoneInfo | str | None) -> ZoneInfo:
    if isinstance(zone, ZoneInfo):
        return zone
    if isinstance(zone, str) and zone:
        return ZoneInfo(zone)
    return UTC


def _normalize_timestamp(value: datetime | date | str, zone: ZoneInfo) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(zone)
    else:
        ts = ts.tz_convert(zone)
    return ts.normalize()


@dataclass(frozen=True)
class Window:
    """Time window represented by inclusive start/end timestamps."""

    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:  # pragma: no cover - defensive guard
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Window timestamps must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("Window start must be strictly before end")

    @property
    def timezone(self) -> ZoneInfo:
        tz = self.start.tzinfo
        if isinstance(tz, ZoneInfo):
            return tz
        return UTC

    @property
    def tz_name(self) -> str:
        return getattr(self.timezone, "key", "UTC")

    def to_dict(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone": self.tz_name,
        }

    @classmethod
    def from_bounds(
        cls,
        *,
        start: datetime | date | str,
        end: datetime | date | str,
        zone: ZoneInfo | str | None = None,
    ) -> "Window":
        tz = _coerce_zone(zone)
        start_ts = _normalize_timestamp(start, tz)
        end_ts = _normalize_timestamp(end, tz)
        return cls(start=start_ts, end=end_ts)

    @classmethod
    def from_duration(
        cls,
        *,
        end: datetime | date | str,
        duration: timedelta,
        zone: ZoneInfo | str | None = None,
    ) -> "Window":
        tz = _coerce_zone(zone)
        end_ts = _normalize_timestamp(end, tz)
        start_ts = end_ts - duration
        return cls(start=start_ts.normalize(), end=end_ts)

    def __iter__(self) -> Iterable[pd.Timestamp]:  # pragma: no cover - convenience
        yield self.start
        yield self.end
