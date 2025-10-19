# src/strategies/mean_reversion.py
# =============================================================================
# Purpose:
#   Generate {-1,0,+1} trading signals using a z-score of Close relative to a
#   rolling mean and standard deviation.
#
# Idea:
#   - If price is far below its recent average, go long (expect reversion up).
#   - If price is far above, go short (expect reversion down).
# =============================================================================
from __future__ import annotations
import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")

def generate_signals(df: pd.DataFrame, lookback: int = 20, z_entry: float = 2.0) -> pd.Series:
    """Return a signal Series aligned to df.index based on z-score extremes.
    
    Signals:
      +1 => long;  -1 => short;  0 => flat.
    """
    close = df["Close"].astype(float)
    ma = close.rolling(lookback, min_periods=lookback).mean()
    sd = close.rolling(lookback, min_periods=lookback).std(ddof=0)
    z = (close - ma) / sd

    sig = pd.Series(0, index=df.index)
    sig[z <= -z_entry] = 1     # statistically cheap
    sig[z >=  z_entry] = -1    # statistically rich
    return sig.astype(int)
