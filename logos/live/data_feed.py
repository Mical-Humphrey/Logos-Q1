"""Live data feed utilities used by the trading runner."""

from __future__ import annotations

import csv
import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Protocol

from .time import TimeProvider

logger = logging.getLogger(__name__)


@dataclass
class Bar:
    """Canonical minute bar structure."""

    dt: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str


class DataFeed(Protocol):
    """Interface implemented by concrete data feeds."""

    def fetch_bars(self, symbol: str, interval: str, since: Optional[dt.datetime]) -> List[Bar]:
        """Return bars newer than ``since`` in ascending order."""


@dataclass
class MemoryBarFeed:
    """Deterministic feed used in unit tests."""

    bars: List[Bar]

    def fetch_bars(self, symbol: str, interval: str, since: Optional[dt.datetime]) -> List[Bar]:
        filtered = [b for b in self.bars if b.symbol == symbol]
        if since is not None:
            filtered = [b for b in filtered if b.dt > since]
        return sorted(filtered, key=lambda x: x.dt)


@dataclass
class CsvBarFeed:
    """Simple feed that tails a CSV file on disk.

    TODO: replace with streaming/websocket consumption once available.
    """

    path: Path
    time_provider: TimeProvider

    def fetch_bars(self, symbol: str, interval: str, since: Optional[dt.datetime]) -> List[Bar]:
        if not self.path.exists():
            return []
        out: List[Bar] = []
        with self.path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("symbol") != symbol:
                    continue
                try:
                    bar_dt = dt.datetime.fromisoformat(row["dt"])
                except (KeyError, ValueError):
                    continue
                if since is not None and bar_dt <= since:
                    continue
                out.append(
                    Bar(
                        dt=bar_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        symbol=symbol,
                    )
                )
        return sorted(out, key=lambda x: x.dt)


CSV_HEADERS = ["dt", "open", "high", "low", "close", "volume", "symbol"]


class FetchError(RuntimeError):
    """Raised when a polling feed exhausts retries without fresh data."""


FetchCallable = Callable[[str, str, Optional[dt.datetime]], Iterable[Bar]]


@dataclass
class FixtureReplayFeed:
    """Deterministic feed that replays bars from an on-disk fixture.

    The feed eagerly reloads the fixture when bars grow stale, retrying up to
    ``max_retries`` times with deterministic logging before raising
    :class:`FetchError`.
    """

    dataset: Path
    time_provider: TimeProvider
    max_age_seconds: float = 300.0
    max_retries: int = 1

    def __post_init__(self) -> None:
        self.dataset = Path(self.dataset)
        self._cache: Dict[str, List[Bar]] = {}

    def fetch_bars(self, symbol: str, interval: str, since: Optional[dt.datetime]) -> List[Bar]:
        attempts = 0
        last_age: Optional[float] = None
        while attempts <= self.max_retries:
            bars = self._load_symbol(symbol)
            if not bars:
                raise FetchError(f"fixture dataset {self.dataset} has no rows for {symbol}")
            last_age = self._age_seconds(bars)
            if last_age <= self.max_age_seconds:
                return [bar for bar in bars if since is None or bar.dt > since]
            logger.warning(
                "fixture replay attempt %s/%s stale fixture data for %s (age=%ss, max_age=%ss)",
                attempts + 1,
                self.max_retries + 1,
                symbol,
                int(last_age),
                int(self.max_age_seconds),
            )
            self._invalidate(symbol)
            attempts += 1
        message = (
            f"stale fixture data for {symbol}: age={int(last_age or -1)}s exceeds "
            f"max_age={int(self.max_age_seconds)}s after {self.max_retries + 1} attempts"
        )
        raise FetchError(message)

    def _load_symbol(self, symbol: str) -> List[Bar]:
        if symbol in self._cache:
            return list(self._cache[symbol])
        if not self.dataset.exists():
            raise FetchError(f"fixture dataset missing at {self.dataset}")
        rows: List[Bar] = []
        with self.dataset.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("symbol") != symbol:
                    continue
                try:
                    bar_dt = dt.datetime.fromisoformat(row["dt"])
                    bar = Bar(
                        dt=bar_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        symbol=symbol,
                    )
                except KeyError as exc:
                    raise FetchError(f"missing column {exc.args[0]} in {self.dataset}") from exc
                except ValueError as exc:
                    raise FetchError(f"invalid bar in {self.dataset}: {row}") from exc
                rows.append(bar)
        rows.sort(key=lambda bar: bar.dt)
        self._cache[symbol] = rows
        return list(rows)

    def _invalidate(self, symbol: str) -> None:
        self._cache.pop(symbol, None)

    def _age_seconds(self, bars: List[Bar]) -> float:
        latest = bars[-1].dt
        now = self.time_provider.utc_now()
        return (now - latest).total_seconds()


@dataclass
class CachedPollingFeed:
    """Tail a local cache and poll a provider when bars fall stale.

    The feed attempts to satisfy requests from the cache. If the most
    recent bar is older than ``max_age"`, it invokes ``provider`` to fetch
    newer data, retrying up to ``max_retries`` times before giving up.
    """

    cache_path: Path
    provider: FetchCallable
    time_provider: TimeProvider
    max_age: float = 90.0
    max_retries: int = 2

    def fetch_bars(self, symbol: str, interval: str, since: Optional[dt.datetime]) -> List[Bar]:
        bars = self._load_cache(symbol)
        if self._is_fresh(bars):
            return [bar for bar in bars if since is None or bar.dt > since]

        last_dt = bars[-1].dt if bars else since
        bars = self._refresh(symbol, interval, last_dt, existing=bars)
        return [bar for bar in bars if since is None or bar.dt > since]

    # ------------------------------------------------------------------
    def _is_fresh(self, bars: List[Bar]) -> bool:
        if not bars:
            return False
        latest = bars[-1].dt
        now = self.time_provider.utc_now()
        age = (now - latest).total_seconds()
        return age <= self.max_age

    def _load_cache(self, symbol: str) -> List[Bar]:
        if not self.cache_path.exists():
            return []
        out: List[Bar] = []
        with self.cache_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("symbol") != symbol:
                    continue
                try:
                    bar_dt = dt.datetime.fromisoformat(row["dt"])
                except (KeyError, ValueError):
                    continue
                out.append(
                    Bar(
                        dt=bar_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        symbol=symbol,
                    )
                )
        out.sort(key=lambda bar: bar.dt)
        return out

    def _refresh(
        self,
        symbol: str,
        interval: str,
        since: Optional[dt.datetime],
        existing: Optional[List[Bar]] = None,
    ) -> List[Bar]:
        attempts = 0
        last_error: Optional[Exception] = None
        merged = list(existing or [])
        while attempts <= self.max_retries:
            try:
                fresh = list(self.provider(symbol, interval, since))
            except Exception as exc:  # pragma: no cover - defensive safety
                last_error = exc
                attempts += 1
                continue
            if fresh:
                merged = self._merge_bars(merged, fresh)
                self._store_cache(merged)
                if self._is_fresh(merged):
                    return merged
                since = merged[-1].dt
            else:
                if self._is_fresh(merged):
                    return merged
            attempts += 1
        message = "exhausted retries fetching fresh bars"
        if last_error:
            message = f"{message}: {last_error}"
        raise FetchError(message)

    def _merge_bars(self, existing: List[Bar], fresh: List[Bar]) -> List[Bar]:
        by_dt = {bar.dt: bar for bar in existing}
        for bar in fresh:
            by_dt[bar.dt] = bar
        merged = sorted(by_dt.values(), key=lambda bar: bar.dt)
        return merged

    def _store_cache(self, bars: List[Bar]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for bar in bars:
                writer.writerow(
                    {
                        "dt": bar.dt.isoformat(),
                        "open": f"{bar.open:.8f}",
                        "high": f"{bar.high:.8f}",
                        "low": f"{bar.low:.8f}",
                        "close": f"{bar.close:.8f}",
                        "volume": f"{bar.volume:.8f}",
                        "symbol": bar.symbol,
                    }
                )

