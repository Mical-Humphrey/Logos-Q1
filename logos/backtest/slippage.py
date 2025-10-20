# src/backtest/slippage.py
# =============================================================================
# Purpose:
#   Naive price adjustment to approximate execution friction (slippage).
#
# Model:
#   fill_price = price * (1 + side * bps/10,000)
#   where side = +1 for buy, -1 for sell.
# =============================================================================
from __future__ import annotations


def apply(price: float, side: int, slip_bps: float = 1.0) -> float:
    """Return adjusted fill price after applying slip_bps basis points."""
    bps = slip_bps / 10_000.0
    return float(price) * (1.0 + side * bps)
