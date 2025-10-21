# src/backtest/engine.py
# =============================================================================
# Purpose:
#   Convert signals into trades, simulate fills and costs, and produce equity,
#   positions, returns, trades, and metrics — now asset-class and interval aware.
#
# New:
#   - 'asset_class' switch for cost handling (equity, crypto, fx)
#   - 'periods_per_year' passed in to metrics for correct annualization
#   - Optional FX spread and crypto fee handling
#
# Simplifications:
#   - Fixed-dollar sizing per trade (no compounding)
#   - Enter/exit on signal changes only
#   - Slippage remains naive bps on price
# =============================================================================
from __future__ import annotations

import logging
from typing import Dict, TypedDict, Union

import numpy as np
import pandas as pd

from .metrics import cagr, sharpe, max_drawdown, win_rate, exposure
from .slippage import apply as slip_price
from .costs import commission_per_share, crypto_fee_usd, fx_spread_price_bump

logger = logging.getLogger(__name__)


class BacktestResult(TypedDict):
    equity_curve: pd.Series
    positions: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    metrics: Dict[str, float]


def run_backtest(
    prices: pd.DataFrame,
    signals: pd.Series,
    dollar_per_trade: float = 10_000,
    slip_bps: float = 1.0,
    commission_per_share_rate: float = 0.0035,
    fee_bps: float = 5.0,  # crypto maker/taker fee
    fx_pip_size: float = 0.0001,  # 0.0001 for EURUSD; 0.01 for USDJPY
    asset_class: str = "equity",
    periods_per_year: int = 252,
) -> BacktestResult:
    """Simulate trading given price data and target signals with asset-aware costs."""
    df = prices.copy().sort_index()
    if df.index.has_duplicates:
        df = df[~df.index.duplicated(keep="last")]
    sig = signals.reindex(df.index).fillna(0).astype(int)
    close = df["Close"].astype(float)

    # Detect changes in desired position direction (delta signals)
    changes = sig - sig.shift(1).fillna(0).astype(int)
    orders_idx = changes.index[changes != 0]
    sides = np.sign(changes.loc[orders_idx]).astype(int)  # +1 buy more, -1 sell more
    ref_prices = close.loc[orders_idx]
    shares = np.floor(dollar_per_trade / ref_prices).astype(int) * sides

    # Position & cash time series (PnL-style account; no starting capital)
    position = pd.Series(0.0, index=df.index)
    cash = pd.Series(0.0, index=df.index)

    # Process each order with asset-aware fill price and fees
    asset = asset_class.lower()

    def _first_position(idx: pd.Index, key: Union[pd.Timestamp, str]) -> int:
        loc = idx.get_loc(key)
        if isinstance(loc, slice):
            start = loc.start
            if start is None:
                raise KeyError(key)
            return int(start)
        if isinstance(loc, np.ndarray):
            if not len(loc):
                raise KeyError(key)
            return int(loc.min())
        return int(loc)

    for t, side, sh in zip(orders_idx, sides, shares):
        if sh == 0:
            continue
        # Base price:
        px = float(close.loc[t])
        # FX spread model (buy pays up, sell receives down)
        if asset in {"fx", "forex"}:
            px = fx_spread_price_bump(
                px, int(side), spread_pips=1.0, pip_size=fx_pip_size
            )

        # Slippage on top
        fill_p = slip_price(px, int(side), slip_bps=slip_bps)

        # Fees/commissions by asset class
        if asset == "equity":
            fee = commission_per_share(int(sh), rate=commission_per_share_rate)
        elif asset == "crypto":
            fee = crypto_fee_usd(fill_p, int(sh), fee_bps=fee_bps)
        elif asset in {"fx", "forex"}:
            # Keep it simple: apply no extra commission (many brokers embed in spread)
            fee = 0.0
        else:
            fee = 0.0

        # Persist position change from time t forward; book cash at t
        start_idx = _first_position(position.index, t)
        span = slice(start_idx, None)
        updated_position = position.iloc[span] + sh
        position.iloc[span] = updated_position

        cash_idx = _first_position(cash.index, t)
        cash.iloc[cash_idx] = cash.iloc[cash_idx] - (sh * fill_p + fee)

    # Equity = cumulative cash + mark-to-market of open position
    mkt_value = position * close
    equity = (cash.cumsum() + mkt_value).ffill()

    # Returns at bar frequency (intraday-friendly)
    returns = equity.pct_change().fillna(0.0)

    # Crude trade PnL proxy: mark realized PnL when absolute position decreases
    trade_marks = position.abs().diff() < 0
    realized = returns.where(trade_marks, 0.0)
    trade_pnl_series = realized * equity.shift(1).bfill()

    metrics = {
        "CAGR": cagr(equity, periods_per_year=periods_per_year),
        "Sharpe": sharpe(returns, periods_per_year=periods_per_year),
        "MaxDD": max_drawdown(equity),
        "WinRate": win_rate(trade_pnl_series[trade_pnl_series != 0.0]),
        "Exposure": exposure(position),
    }

    trades = pd.DataFrame(
        {
            "time": list(orders_idx),
            "side": list(sides),
            "shares": list(shares),
            "ref_close": list(ref_prices.astype(float)),
        }
    )

    return {
        "equity_curve": equity,
        "positions": position,
        "returns": returns,
        "trades": trades,
        "metrics": metrics,
    }
