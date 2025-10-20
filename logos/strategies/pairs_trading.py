# src/strategies/pairs_trading.py
# =============================================================================
# Purpose:
#   Statistical arbitrage between two correlated assets.
#
# Idea:
#   - If two series move together historically (high correlation), their
#     spread (A - beta*B) may mean-revert. We trade z-score extremes of this spread.
#
# Outputs:
#   Returns a DataFrame with columns: ['spread','zscore','signal_A','signal_B']
# =============================================================================
from __future__ import annotations
import pandas as pd
import numpy as np
import logging
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")

logger = logging.getLogger(__name__)


def generate_signals(
    df: pd.DataFrame,
    symA: str = "MSFT",
    symB: str | None = None,
    lookback: int = 30,
    z_entry: float = 2.0,
    z_exit: float = 0.5,
    hedge_ratio: float | None = None,
    window: int | None = None,
    threshold: float | None = None,
    **_: float,
) -> pd.Series:
    """Generate {-1,0,+1} pairs trading style signals.

    When both ``symA`` and ``symB`` columns are present the classic spread
    A - beta * B is used. Otherwise the function gracefully falls back to a
    mean-reverting spread derived from the available ``Close`` column so the
    CLI example commands remain operational even with single-symbol data.
    """
    close_cols = {c.lower(): c for c in df.columns}

    if symA in df.columns and symB and symB in df.columns:
        price_a = df[symA].astype(float)
        price_b = df[symB].astype(float)
    elif "close" in close_cols:
        # Single-symbol fallback: synthetically derive a partner series
        price_a = df[close_cols["close"]].astype(float)
        ratio = hedge_ratio if hedge_ratio is not None else 1.0
        price_b = price_a.shift(1).bfill() * ratio
    else:
        # Take the first numeric column as a proxy price series
        numeric_cols = df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) == 0:
            raise ValueError("pairs_trading requires at least one numeric price column")
        price_a = df[numeric_cols[0]].astype(float)
        price_b = price_a.shift(1).bfill()

    if window is not None:
        lookback = int(window)
    if threshold is not None:
        z_entry = float(threshold)
        z_exit = min(z_exit, z_entry / 2)

    beta = (
        hedge_ratio if hedge_ratio is not None else np.polyfit(price_b, price_a, 1)[0]
    )
    spread = price_a - beta * price_b

    mean = spread.rolling(lookback, min_periods=lookback).mean()
    std = spread.rolling(lookback, min_periods=lookback).std(ddof=0)
    z = (spread - mean) / std

    long_sig = z <= -z_entry
    short_sig = z >= z_entry
    exit_sig = z.abs() <= z_exit

    position = 0
    sig = pd.Series(0, index=df.index)
    for idx in range(len(sig)):
        if long_sig.iloc[idx]:
            position = 1
        elif short_sig.iloc[idx]:
            position = -1
        elif exit_sig.iloc[idx]:
            position = 0
        sig.iloc[idx] = position

    return sig.astype(int)
