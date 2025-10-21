# src/backtest/metrics.py
# =============================================================================
# Purpose:
#   Standard performance metrics for strategy evaluation with explicit
#   control of annualization via 'periods_per_year'.
#
# Metrics:
#   - CAGR, Sharpe, MaxDD, WinRate, Exposure
#
# Notes:
#   - The engine supplies 'periods_per_year' based on asset-class + interval.
#   - Functions are defensive: empty inputs return 0.0 to keep backtests flowing.
# =============================================================================
from __future__ import annotations

import numpy as np
import pandas as pd

from logos.utils.data_hygiene import ensure_no_object_dtype, require_datetime_index


def cagr(equity: pd.Series, periods_per_year: int) -> float:
    require_datetime_index(equity, context="backtest.metrics.cagr(equity)")
    ensure_no_object_dtype(equity, context="backtest.metrics.cagr(equity)")
    eq = equity.dropna().astype(float)
    if eq.empty:
        return 0.0
    start, end = float(eq.iloc[0]), float(eq.iloc[-1])
    years = len(eq) / max(1, periods_per_year)
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def sharpe(returns: pd.Series, periods_per_year: int, risk_free: float = 0.0) -> float:
    require_datetime_index(returns, context="backtest.metrics.sharpe(returns)")
    rets = returns.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if len(rets) == 0 or rets.std(ddof=0) == 0:
        return 0.0
    excess = rets - (risk_free / periods_per_year)
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=0))


def max_drawdown(equity: pd.Series) -> float:
    require_datetime_index(equity, context="backtest.metrics.max_drawdown(equity)")
    ensure_no_object_dtype(equity, context="backtest.metrics.max_drawdown(equity)")
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
    require_datetime_index(positions, context="backtest.metrics.exposure(positions)")
    ensure_no_object_dtype(positions, context="backtest.metrics.exposure(positions)")
    pos = positions.fillna(0).abs()
    if len(pos) == 0:
        return 0.0
    return float((pos > 0).mean())
