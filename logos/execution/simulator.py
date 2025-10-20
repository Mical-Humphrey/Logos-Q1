# src/execution/simulator.py
# =============================================================================
# Purpose:
#   Convert signal changes into discrete orders with fixed-dollar sizing.
#   Kept as a separate module to document the transformation step and for
#   potential reuse in alternative engines.
# =============================================================================
from __future__ import annotations
import numpy as np
import pandas as pd


def signals_to_orders(
    signals: pd.Series,
    prices: pd.Series,
    dollar_per_trade: float = 10_000,
) -> pd.DataFrame:
    """Map signal deltas to orders (side, shares, ref_price)."""
    sig = signals.fillna(0).astype(int)
    changes = sig - sig.shift(1).fillna(0).astype(int)
    idx = changes.index[changes != 0]
    side = np.sign(changes.loc[idx]).astype(int)
    ref = prices.loc[idx].astype(float)
    shares = np.floor(dollar_per_trade / ref).astype(int) * side
    return pd.DataFrame({"side": side, "shares": shares, "ref_price": ref}, index=idx)
