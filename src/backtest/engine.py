# src/backtest/engine.py
# =============================================================================
# Purpose:
#   Convert signals into trades, simulate fills/costs, and produce equity,
#   positions, returns, trades, and metrics.
#
# Simplifications (on purpose for learning):
#   - Fixed-dollar sizing per trade (no compounding),
#   - Enter/exit on signal *changes* only,
#   - Naive per-share commission + bps slippage.
#
# Extension ideas:
#   - Add starting capital and compounding,
#   - Volatility-targeted position sizing,
#   - Multi-symbol portfolio accounting,
#   - Better trade matching for exact realized PnL.
# =============================================================================
from __future__ import annotations
import logging
from typing import Dict
import numpy as np
import pandas as pd

from .metrics import cagr, sharpe, max_drawdown, win_rate, exposure
from .slippage import apply as slip_price
from .costs import commission_per_share

logger = logging.getLogger(__name__)

def run_backtest(
    prices: pd.DataFrame,
    signals: pd.Series,
    dollar_per_trade: float = 10_000,
    slip_bps: float = 1.0,
    commission_per_share_rate: float = 0.0035,
) -> Dict[str, object]:
    """Simulate daily-bar trading given price data and target signals.
    
    Parameters
    ----------
    prices : DataFrame with 'Close' column
    signals: Series of {-1,0,+1} desired direction
    dollar_per_trade: fixed notional per order
    slip_bps: slippage in basis points per order
    commission_per_share_rate: dollar commission per share
    
    Returns
    -------
    dict with keys: equity_curve, positions, returns, trades, metrics
    """
    df = prices.copy().sort_index()
    sig = signals.reindex(df.index).fillna(0).astype(int)
    close = df["Close"].astype(float)

    # Detect changes in desired position direction (delta signals)
    changes = sig - sig.shift(1).fillna(0).astype(int)
    orders_idx = changes.index[changes != 0]
    sides = np.sign(changes.loc[orders_idx]).astype(int)      # +1 buy more, -1 sell more
    ref_prices = close.loc[orders_idx]
    shares = np.floor(dollar_per_trade / ref_prices).astype(int) * sides

    # Position & cash time series (PnL-style account; no starting capital)
    position = pd.Series(0.0, index=df.index)
    cash = pd.Series(0.0, index=df.index)

    for t, side, sh in zip(orders_idx, sides, shares):
        if sh == 0:
            continue
        fill_p = slip_price(float(close.loc[t]), int(side), slip_bps=slip_bps)
        fee = commission_per_share(int(sh), rate=commission_per_share_rate)
        # Persist position change from time t forward; book cash impact at t
        position.loc[t:] += sh
        cash.loc[t] -= sh * fill_p + fee

    # Equity = cumulative cash + mark-to-market of open position
    mkt_value = position * close
    equity = (cash.cumsum() + mkt_value).ffill()
    returns = equity.pct_change().fillna(0.0)

    # Crude trade PnL proxy: mark realized PnL when absolute position decreases
    trade_marks = (position.abs().diff() < 0)
    realized = returns.where(trade_marks, 0.0)
    trade_pnl_series = (realized * equity.shift(1).bfill())

    metrics = {
        "CAGR":    cagr(equity),
        "Sharpe":  sharpe(returns),
        "MaxDD":   max_drawdown(equity),
        "WinRate": win_rate(trade_pnl_series[trade_pnl_series != 0.0]),
        "Exposure":exposure(position),
    }

    trades = pd.DataFrame({
        "time": list(orders_idx),
        "side": list(sides),
        "shares": list(shares),
        "ref_close": list(ref_prices.astype(float)),
    })

    return {
        "equity_curve": equity,
        "positions": position,
        "returns": returns,
        "trades": trades,
        "metrics": metrics,
    }
