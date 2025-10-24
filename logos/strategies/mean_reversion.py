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

import math
from typing import Any, Dict

import pandas as pd
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")


def generate_signals(
    df: pd.DataFrame, lookback: int = 20, z_entry: float = 2.0
) -> pd.Series:
    """Return a signal Series aligned to df.index based on z-score extremes.

    Signals:
      +1 => long;  -1 => short;  0 => flat.
    """
    close = df["Close"].astype(float)
    ma = close.rolling(lookback, min_periods=lookback).mean()
    sd = close.rolling(lookback, min_periods=lookback).std(ddof=0)
    z = (close - ma) / sd

    sig = pd.Series(0, index=df.index, dtype=int)
    sig.loc[z <= -z_entry] = 1  # statistically cheap
    sig.loc[z >= z_entry] = -1  # statistically rich
    return sig.astype(int)


def explain(
  df: pd.DataFrame,
  *,
  timestamp: pd.Timestamp | str | None = None,
  lookback: int = 20,
  z_entry: float = 2.0,
  direction: str | int | None = None,
) -> Dict[str, Any]:
  """Describe the latest mean-reversion decision near ``timestamp``."""

  if df.empty or "Close" not in df.columns:
    return {"reason": "No price data available for explanation."}

  close = df["Close"].astype(float).copy()
  idx = close.index
  if not isinstance(idx, pd.DatetimeIndex):
    close.index = pd.to_datetime(idx)
    idx = close.index

  ts = pd.Timestamp(timestamp) if timestamp is not None else idx[-1]
  if idx.tz is None and ts.tzinfo is not None:
    ts = ts.tz_localize(None)
  if idx.tz is not None and ts.tzinfo is None:
    ts = ts.tz_localize(idx.tz)
  elif idx.tz is not None and ts.tzinfo is not None:
    ts = ts.tz_convert(idx.tz)

  target = idx.asof(ts)
  if target is pd.NaT:
    target = idx[-1]

  ma = close.rolling(lookback, min_periods=lookback).mean()
  sd = close.rolling(lookback, min_periods=lookback).std(ddof=0)
  price = float(close.loc[target])
  mean_val = float(ma.loc[target]) if pd.notna(ma.loc[target]) else math.nan
  std_val = float(sd.loc[target]) if pd.notna(sd.loc[target]) else math.nan

  if not math.isfinite(mean_val) or not math.isfinite(std_val) or std_val == 0.0:
    return {
      "timestamp": target,
      "price": price,
      "reason": "Insufficient history to compute z-score at this timestamp.",
    }

  z_score = (price - mean_val) / std_val
  intent = direction
  if intent is None:
    intent = "long" if z_score <= -abs(z_entry) else "short" if z_score >= abs(z_entry) else "flat"
  elif isinstance(intent, int):
    intent = "long" if intent > 0 else "short" if intent < 0 else "flat"

  threshold = -abs(z_entry) if intent == "long" else abs(z_entry)

  return {
    "timestamp": target,
    "price": price,
    "mean": mean_val,
    "std": std_val,
    "z_score": z_score,
    "threshold": threshold,
    "direction": intent,
  }
