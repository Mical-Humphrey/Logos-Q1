# src/backtest/metrics.py
# =============================================================================
# Purpose:
#   Standard performance metrics for strategy evaluation.
#
# Metrics Implemented:
#   - CAGR      : compound annual growth rate
#   - Sharpe    : risk-adjusted return (annualized)
#   - MaxDD     : maximum drawdown (worst peak-to-trough)
#   - WinRate   : percent of winning trades (proxy here via trade PnL events)
#   - Exposure  : fraction of time in the market
#
# Notes:
#   - Assumes daily bars (252 trading days/year) for annualization.
#   - Functions are defensive: empty inputs return 0.0 rather than error.
# =============================================================================
from __future__ import annotations
import numpy as np
import pandas as pd

def cagr(equity: pd.Series, periods_per_year: int = 252) -> float:
    equity = equity.dropna()
    if equity.empty:
        return 0.0
    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    years = len(equity) / periods_per_year
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0

def sharpe(returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    rets = returns.dropna()
    if len(rets) == 0 or rets.std(ddof=0) == 0:
        return 0.0
    excess = rets - risk_free / periods_per_year
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=0))

def max_drawdown(equity: pd.Series) -> float:
    eq = equity.dropna().astype(float)
    if eq.empty:
        return 0.0
    peak = eq.cummax()
    dd = (eq / peak) - 1.0
    return float(dd.min())

def win_rate(trade_pnls: pd.Series) -> float:
    pnl = trade_pnls.dropna()
    if len(pnl) == 0:
        return 0.0
    return float((pnl > 0).mean())

def exposure(positions: pd.Series) -> float:
    pos = positions.fillna(0).abs()
    if len(pos) == 0:
        return 0.0
    return float((pos > 0).mean())
