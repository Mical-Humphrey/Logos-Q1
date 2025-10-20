"""Live data feed utilities used by the trading runner."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Protocol

from .time import TimeProvider


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
