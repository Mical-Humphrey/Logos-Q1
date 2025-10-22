"""NYSE trading calendar helpers with deterministic windows.

The utilities here provide a light-weight subset of the official NYSE
schedule focused on daily sessions. They intentionally avoid external
calendar dependencies to keep the project self-contained while still
respecting common full-day closures and 1pm ET early closes. The module
covers the 2024–2025 horizon used by the regression fixtures; future
periods can be appended cheaply as needed.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import List

from logos.window import Window

_NY_TZ = ZoneInfo("America/New_York")
_OPEN_TIME = time(9, 30)
_CLOSE_TIME = time(16, 0)
_EARLY_CLOSE_TIME = time(13, 0)

# Select holiday coverage for the current runbook horizon. The set can be
# extended in-place without impacting existing callers.
_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 1),  # New Year's Day
    date(2024, 1, 15),  # Martin Luther King Jr. Day
    date(2024, 2, 19),  # Presidents' Day
    date(2024, 3, 29),  # Good Friday
    date(2024, 5, 27),  # Memorial Day
    date(2024, 6, 19),  # Juneteenth
    date(2024, 7, 4),  # Independence Day
    date(2024, 9, 2),  # Labor Day
    date(2024, 11, 28),  # Thanksgiving
    date(2024, 12, 25),  # Christmas Day
    # 2025
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
}

# Common 1pm ET early closes. These only shorten the regular session and do
# not change whether a day counts towards the trading calendar.
_EARLY_CLOSE_DATES: set[date] = {
    date(2024, 7, 3),
    date(2024, 11, 29),
    date(2024, 12, 24),
    date(2025, 7, 3),
    date(2025, 11, 28),
    date(2025, 12, 24),
}


def _coerce_zone(zone: ZoneInfo | str | None) -> ZoneInfo:
    if isinstance(zone, ZoneInfo):
        return zone
    if isinstance(zone, str) and zone:
        return ZoneInfo(zone)
    return _NY_TZ


def is_trading_day(session: date) -> bool:
    """Return ``True`` when *session* is a regular NYSE trading day."""

    if session.weekday() >= 5:  # Saturday/Sunday
        return False
    return session not in _HOLIDAYS


def trading_days(start: date, end: date) -> List[date]:
    """Return all NYSE trading days in the inclusive range ``[start, end]``."""

    if end < start:
        raise ValueError("end must be on or after start")
    days: List[date] = []
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        if is_trading_day(current):
            days.append(current)
        current += one_day
    return days


def session_close_time(session: date) -> time:
    """Return the scheduled closing time for *session* in local NY time."""

    return _EARLY_CLOSE_TIME if session in _EARLY_CLOSE_DATES else _CLOSE_TIME


def session_window(session: date, *, tz: ZoneInfo | str | None = None) -> Window | None:
    """Return the trading window for *session* or ``None`` if markets are closed."""

    if not is_trading_day(session):
        return None
    zone = _coerce_zone(tz)
    open_dt = datetime.combine(session, _OPEN_TIME, tzinfo=zone)
    close_dt = datetime.combine(session, session_close_time(session), tzinfo=zone)
    return Window.from_bounds(start=open_dt, end=close_dt, zone=zone)


__all__ = [
    "is_trading_day",
    "trading_days",
    "session_close_time",
    "session_window",
]
