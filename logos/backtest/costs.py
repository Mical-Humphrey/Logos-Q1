# src/backtest/costs.py
# =============================================================================
# Purpose:
#   Cost models for different asset classes.
#
# Models:
#   - Equities: commission per share (dollars) + slippage (handled separately)
#   - Crypto  : maker/taker fee in basis points (bps) applied to notional
#   - FX      : spread in pips (converted to an effective price bump), optional
#
# Notes:
#   - 1 bps = 0.01% = 0.0001 in fractional terms
#   - FX pip size: 0.0001 for most, 0.01 for JPY pairs (USDJPY, EURJPY, ...)
# =============================================================================
from __future__ import annotations


def commission_per_share(shares: int, rate: float = 0.0035) -> float:
    """Dollar commission computed as |shares| * rate (equities)."""
    return abs(int(shares)) * float(rate)


def crypto_fee_usd(fill_price: float, shares: int, fee_bps: float) -> float:
    """Fee in USD for crypto at fee_bps of notional (maker/taker)."""
    notional = abs(shares) * float(fill_price)
    return notional * (fee_bps / 10_000.0)


def fx_spread_price_bump(
    price: float, side: int, spread_pips: float, pip_size: float
) -> float:
    """Return a price adjusted by the spread (simple model).
    Buy pays up; sell receives down. side=+1 buy, -1 sell.
    """
    bump = spread_pips * pip_size
    return float(price) + side * bump
