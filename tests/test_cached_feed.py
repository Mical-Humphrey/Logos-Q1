import csv
import datetime as dt
from pathlib import Path

import pytest

from logos.live.data_feed import Bar, CachedPollingFeed, CSV_HEADERS, FetchError
from logos.live.time import MockTimeProvider


def _write_cache(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "dt": bar.dt.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "symbol": bar.symbol,
                }
            )


def test_cached_feed_serves_fresh_data_without_polling(tmp_path: Path) -> None:
    now = dt.datetime(2025, 1, 1, 9, 35, tzinfo=dt.timezone.utc)
    clock = MockTimeProvider(current=now)
    cache_path = tmp_path / "cache.csv"
    bars = [
        Bar(dt=dt.datetime(2025, 1, 1, 9, 33, tzinfo=dt.timezone.utc), open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 34, tzinfo=dt.timezone.utc), open=100.5, high=101.5, low=99.5, close=101, volume=1_100, symbol="MSFT"),
    ]
    _write_cache(cache_path, bars)
    provider_calls: list[tuple[str, str, dt.datetime | None]] = []

    def provider(symbol: str, interval: str, since: dt.datetime | None):
        provider_calls.append((symbol, interval, since))
        return []

    feed = CachedPollingFeed(cache_path=cache_path, provider=provider, time_provider=clock, max_age=180)
    fetched = feed.fetch_bars("MSFT", "1m", since=None)

    assert fetched == bars
    assert provider_calls == []


def test_cached_feed_refreshes_stale_data(tmp_path: Path) -> None:
    now = dt.datetime(2025, 1, 1, 9, 35, tzinfo=dt.timezone.utc)
    clock = MockTimeProvider(current=now)
    cache_path = tmp_path / "cache.csv"
    stale_bar = Bar(dt=dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc), open=99, high=100, low=98, close=99.5, volume=800, symbol="MSFT")
    _write_cache(cache_path, [stale_bar])

    new_bars = [
        Bar(dt=dt.datetime(2025, 1, 1, 9, 34, tzinfo=dt.timezone.utc), open=100, high=101, low=99, close=100.5, volume=1_000, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 35, tzinfo=dt.timezone.utc), open=100.6, high=101.6, low=99.6, close=101.1, volume=1_050, symbol="MSFT"),
    ]
    provider_calls: list[tuple[str, str, dt.datetime | None]] = []

    def provider(symbol: str, interval: str, since: dt.datetime | None):
        provider_calls.append((symbol, interval, since))
        return new_bars

    feed = CachedPollingFeed(cache_path=cache_path, provider=provider, time_provider=clock, max_age=60, max_retries=1)
    fetched = feed.fetch_bars("MSFT", "1m", since=stale_bar.dt)

    assert fetched == new_bars
    assert len(provider_calls) == 1
    with cache_path.open("r", encoding="utf-8") as fh:
        written_rows = list(csv.DictReader(fh))
    assert len(written_rows) == 3  # stale row plus two fresh rows


def test_cached_feed_raises_after_retry_exhaustion(tmp_path: Path) -> None:
    now = dt.datetime(2025, 1, 1, 9, 35, tzinfo=dt.timezone.utc)
    clock = MockTimeProvider(current=now)
    cache_path = tmp_path / "cache.csv"
    _write_cache(cache_path, [])

    attempts: list[int] = []

    def provider(symbol: str, interval: str, since: dt.datetime | None):
        attempts.append(1)
        raise RuntimeError("network down")

    feed = CachedPollingFeed(cache_path=cache_path, provider=provider, time_provider=clock, max_age=60, max_retries=1)

    with pytest.raises(FetchError):
        feed.fetch_bars("MSFT", "1m", since=None)

    assert len(attempts) == 2  # initial + retry
