"""Soft performance budgets for key hot paths.

These tests surface regressions in tight loops while remaining deterministic.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from logos.cli import _plot_equity
from logos.metrics import cagr, exposure, max_drawdown, sharpe, sortino, volatility


def _print_timing(label: str, duration: float, *, budget: float, details: str) -> None:
    print(f"[perf] {label} duration={duration:.6f}s budget={budget:.2f}s {details}")


def test_metrics_perf_budget() -> None:
    """Ensure metrics run within the soft budget on 10k daily bars."""

    seed = 514
    periods = 10_000
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2000-01-01", periods=periods, freq="1D", tz="UTC")
    returns = pd.Series(rng.normal(loc=0.0003, scale=0.01, size=periods), index=dates)
    equity = pd.Series(np.cumprod(1.0 + returns.to_numpy()), index=dates)
    positions = pd.Series(np.where(rng.random(periods) > 0.6, 1.0, 0.0), index=dates)

    budget = 0.7
    start = time.perf_counter()
    _ = cagr(equity)
    _ = volatility(returns)
    _ = sharpe(returns)
    _ = sortino(returns)
    _ = max_drawdown(equity)
    _ = exposure(positions)
    duration = time.perf_counter() - start

    _print_timing(
        "metrics-10k-bars",
        duration,
        budget=budget,
        details=f"seed={seed} rows={periods}",
    )
    assert (
        duration <= budget
    ), f"metrics exceeded budget: {duration:.4f}s > {budget:.2f}s"


def test_minute_bar_parse_and_filter(tmp_path: Path) -> None:
    """Exercise minute-bar parsing and filtering on ~50k rows."""

    seed = 1337
    rows = 50_000
    rng = np.random.default_rng(seed)
    start_dt = pd.Timestamp("2024-01-01 09:30", tz="UTC")
    idx = pd.date_range(start=start_dt, periods=rows, freq="1min")

    frame = pd.DataFrame(
        {
            "dt": idx,
            "open": rng.normal(100.0, 1.0, size=rows),
            "high": rng.normal(100.5, 1.0, size=rows),
            "low": rng.normal(99.5, 1.0, size=rows),
            "close": rng.normal(100.2, 1.0, size=rows),
            "volume": rng.integers(750, 2500, size=rows),
            "symbol": "MSFT",
        }
    )

    csv_path = tmp_path / "minute_50k.csv"
    frame.to_csv(csv_path, index=False)

    window_end = start_dt + pd.Timedelta(minutes=rows // 2)
    window_start = window_end - pd.Timedelta(minutes=10_000)

    budget = 2.0
    start = time.perf_counter()
    parsed = pd.read_csv(csv_path, parse_dates=["dt"])
    if parsed["dt"].dt.tz is None:
        parsed["dt"] = parsed["dt"].dt.tz_localize("UTC")
    else:
        parsed["dt"] = parsed["dt"].dt.tz_convert("UTC")
    filtered = parsed.loc[(parsed["dt"] >= window_start) & (parsed["dt"] <= window_end)]
    _ = filtered.agg({"open": "mean", "close": "mean", "volume": "sum"})
    duration = time.perf_counter() - start

    _print_timing(
        "minute-parse-filter-50k",
        duration,
        budget=budget,
        details=f"seed={seed} rows={rows} path={csv_path}",
    )
    assert (
        duration <= budget
    ), f"minute parse exceeded budget: {duration:.4f}s > {budget:.1f}s"


def test_plot_generation_budget() -> None:
    """Ensure plotting stays fast once data hygiene guards pass."""

    seed = 777
    periods = 5_000
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=periods, freq="1D", tz="UTC")
    values = np.cumprod(1.0 + rng.normal(0.0005, 0.012, size=periods)) * 100_000.0
    equity = pd.Series(values, index=dates)

    budget = 0.2
    if sys.gettrace() is not None:
        budget = 0.3  # coverage and tracing slow matplotlib rendering
    start = time.perf_counter()
    fig = _plot_equity(equity)
    duration = time.perf_counter() - start

    _print_timing(
        "plot-equity-figure",
        duration,
        budget=budget,
        details=f"seed={seed} rows={periods}",
    )

    try:
        assert (
            duration <= budget
        ), f"plot generation exceeded budget: {duration:.4f}s > {budget:.1f}s"
    finally:
        plt.close(fig)
