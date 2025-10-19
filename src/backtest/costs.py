# src/backtest/costs.py
# =============================================================================
# Purpose:
#   Minimal commission model used by the engine.
#
# Model:
#   commission_dollars = |shares| * rate
# =============================================================================
from __future__ import annotations

def commission_per_share(shares: int, rate: float = 0.0035) -> float:
    """Dollar commission computed as |shares| * rate."""
    return abs(int(shares)) * float(rate)
