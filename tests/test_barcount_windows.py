from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from logos.data_loader import get_prices
from logos.window import Window


NY = ZoneInfo("America/New_York")


def _build_window(start: str, end: str) -> Window:
    return Window.from_bounds(
        start=datetime.fromisoformat(start).replace(tzinfo=NY),
        end=datetime.fromisoformat(end).replace(tzinfo=NY),
        zone=NY,
    )


def test_barcount_dst_transition_window() -> None:
    window = _build_window("2024-10-31T00:00:00", "2024-11-08T00:00:00")
    prices = get_prices("MSFT", window, interval="1d")
    expected_dates = pd.to_datetime(
        [
            "2024-10-31",
            "2024-11-01",
            "2024-11-04",
            "2024-11-05",
            "2024-11-06",
            "2024-11-07",
            "2024-11-08",
        ]
    )
    assert len(prices) == len(expected_dates)
    pd.testing.assert_index_equal(prices.index, expected_dates, check_names=False)


def test_barcount_leap_day_window() -> None:
    window = _build_window("2024-02-28T00:00:00", "2024-03-04T00:00:00")
    prices = get_prices("MSFT", window, interval="1d")
    expected_dates = pd.to_datetime(
        ["2024-02-28", "2024-02-29", "2024-03-01", "2024-03-04"]
    )
    assert len(prices) == len(expected_dates)
    pd.testing.assert_index_equal(prices.index, expected_dates, check_names=False)


def test_barcount_month_end_boundary_window() -> None:
    window = _build_window("2024-07-31T00:00:00", "2024-08-02T00:00:00")
    prices = get_prices("MSFT", window, interval="1d")
    expected_dates = pd.to_datetime(["2024-07-31", "2024-08-01", "2024-08-02"])
    assert len(prices) == len(expected_dates)
    pd.testing.assert_index_equal(prices.index, expected_dates, check_names=False)
