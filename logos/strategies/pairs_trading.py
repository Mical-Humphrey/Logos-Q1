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
    symB: str = "AAPL",
    lookback: int = 30,
    z_entry: float = 2.0,
    z_exit: float = 0.5,
) -> pd.DataFrame:
    """Generate pair trading signals for two correlated equities.

    Assumptions:
      - df contains columns for symA and symB Close prices
      - We use a simple OLS slope (via polyfit) as the hedge ratio

    Signals interpretation:
      - signal_A = +1 and signal_B = -1  => long A / short B
      - signal_A = -1 and signal_B = +1  => short A / long B
      - signal_* = 0 => flat
    """
    if symA not in df.columns or symB not in df.columns:
        raise ValueError(f"DataFrame must contain columns '{symA}' and '{symB}'")

    priceA = df[symA].astype(float)
    priceB = df[symB].astype(float)

    # Hedge ratio: how many shares of B hedge one share of A (slope of A~B)
    beta = np.polyfit(priceB, priceA, 1)[0]
    spread = priceA - beta * priceB

    mean = spread.rolling(lookback, min_periods=lookback).mean()
    std  = spread.rolling(lookback, min_periods=lookback).std(ddof=0)
    z = (spread - mean) / std

    long_sig  = z <= -z_entry
    short_sig = z >=  z_entry
    exit_sig  = z.abs() < z_exit

    # Stateful position: enters on signal, exits when near mean
    position = 0
    pos_series = pd.Series(0, index=df.index)
    for i in range(len(pos_series)):
        if long_sig.iloc[i]:
            position = 1
        elif short_sig.iloc[i]:
            position = -1
        elif exit_sig.iloc[i]:
            position = 0
        pos_series.iloc[i] = position

    signals = pd.DataFrame({
        "spread": spread,
        "zscore": z,
        f"signal_{symA}": pos_series,
        f"signal_{symB}": -pos_series,
    })
    return signals
