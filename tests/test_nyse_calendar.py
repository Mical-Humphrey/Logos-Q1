from __future__ import annotations

from datetime import date

import pytest

from logos.utils.nyse_calendar import (
    is_trading_day,
    session_close_time,
    session_window,
    trading_days,
)


def test_calendar_skips_holidays_and_weekends() -> None:
    days = trading_days(date(2024, 7, 3), date(2024, 7, 5))
    assert days == [date(2024, 7, 3), date(2024, 7, 5)]
    assert is_trading_day(date(2024, 7, 4)) is False


def test_calendar_handles_zero_bar_weekends() -> None:
    assert session_window(date(2024, 3, 9)) is None  # Saturday before DST


def test_nyse_session_window_handles_dst_transition() -> None:
    window = session_window(date(2024, 3, 11))
    assert window is not None
    start_utc, end_utc = window.bounds("UTC")
    assert pytest.approx((end_utc - start_utc).total_seconds(), rel=1e-6) == 6.5 * 3600


def test_nyse_session_window_early_close_hours() -> None:
    window = session_window(date(2024, 11, 29))
    assert window is not None
    start_utc, end_utc = window.bounds("UTC")
    assert pytest.approx((end_utc - start_utc).total_seconds(), rel=1e-6) == 3.5 * 3600
    assert session_close_time(date(2024, 11, 29)).hour == 13


def test_trading_days_requires_increasing_range() -> None:
    with pytest.raises(ValueError, match="end must be on or after start"):
        trading_days(date(2024, 1, 10), date(2024, 1, 1))
