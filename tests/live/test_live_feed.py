from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import pytest

from logos.live.data_feed import FetchError, FixtureReplayFeed
from logos.live.time import MockTimeProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live"


@pytest.fixture()
def fixture_path() -> Path:
    return FIXTURES / "aapl_1m_fixture.csv"


@pytest.fixture()
def fresh_clock() -> MockTimeProvider:
    return MockTimeProvider(current=dt.datetime(2024, 1, 1, 9, 32, 30, tzinfo=dt.timezone.utc))


def test_fixture_feed_replays_bars_in_order(fixture_path: Path, fresh_clock: MockTimeProvider) -> None:
    feed = FixtureReplayFeed(
        dataset=fixture_path,
        time_provider=fresh_clock,
        max_age_seconds=300,
        max_retries=2,
    )

    bars = feed.fetch_bars("AAPL", "1m", since=None)

    assert [bar.dt.isoformat() for bar in bars] == [
        "2024-01-01T09:30:00+00:00",
        "2024-01-01T09:31:00+00:00",
        "2024-01-01T09:32:00+00:00",
    ]
    assert [bar.close for bar in bars] == [100.5, 101.0, 101.2]


def test_fixture_feed_filters_since(fixture_path: Path, fresh_clock: MockTimeProvider) -> None:
    feed = FixtureReplayFeed(
        dataset=fixture_path,
        time_provider=fresh_clock,
        max_age_seconds=600,
        max_retries=1,
    )

    since = dt.datetime(2024, 1, 1, 9, 31, tzinfo=dt.timezone.utc)
    bars = feed.fetch_bars("AAPL", "1m", since=since)

    assert len(bars) == 1
    assert bars[0].dt.isoformat() == "2024-01-01T09:32:00+00:00"


def test_fixture_feed_stale_raises_fetch_error(fixture_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = MockTimeProvider(current=dt.datetime(2024, 1, 1, 9, 40, tzinfo=dt.timezone.utc))
    feed = FixtureReplayFeed(
        dataset=fixture_path,
        time_provider=clock,
        max_age_seconds=60,
        max_retries=2,
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(FetchError) as exc:
            feed.fetch_bars("AAPL", "1m", since=None)

    assert "stale fixture data for AAPL" in str(exc.value)
    attempts = [record for record in caplog.records if "fixture replay attempt" in record.message]
    assert len(attempts) == 3


def test_fixture_feed_missing_file_raises(fresh_clock: MockTimeProvider, tmp_path: Path) -> None:
    dataset_path = tmp_path / "missing.csv"
    feed = FixtureReplayFeed(
        dataset=dataset_path,
        time_provider=fresh_clock,
    )

    with pytest.raises(FetchError) as exc:
        feed.fetch_bars("AAPL", "1m", since=None)

    assert "dataset missing" in str(exc.value)
