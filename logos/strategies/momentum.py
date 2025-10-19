# src/strategies/momentum.py
# =============================================================================
# Purpose:
#   Simple momentum via SMA crossover of Close.
#
# Idea:
#   - When fast SMA rises above slow SMA => trend up => long
#   - When fast SMA falls below slow SMA => trend down => short
# =============================================================================
from __future__ import annotations
import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")

def generate_signals(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    """Return {-1,0,+1} signals from SMA crossover."""
    close = df["Close"].astype(float)
    sma_f = close.rolling(fast, min_periods=fast).mean()
    sma_s = close.rolling(slow, min_periods=slow).mean()
    raw = (sma_f > sma_s).astype(int) - (sma_f < sma_s).astype(int)
    return raw.reindex(df.index).fillna(0).astype(int)
