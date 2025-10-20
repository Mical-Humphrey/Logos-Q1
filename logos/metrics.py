from __future__ import annotations
import math
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _clean_returns(r: pd.Series) -> pd.Series:
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if r.std(ddof=0) == 0:
        return pd.Series([], dtype=float)
    return r


def cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    equity = equity.replace([np.inf, -np.inf], np.nan).dropna()
    if equity.empty:
        return 0.0
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max(len(equity) / periods_per_year, 1e-9)
    return (1 + total_return) ** (1 / years) - 1


def volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    r = _clean_returns(returns)
    if r.empty:
        return 0.0
    return float(r.std(ddof=0) * math.sqrt(periods_per_year))


def sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    r = _clean_returns(returns)
    if r.empty:
        return 0.0
    excess = r - (risk_free_rate / periods_per_year)
    vol = r.std(ddof=0)
    if vol == 0:
        return 0.0
    return float(excess.mean() / vol * math.sqrt(periods_per_year))


def sortino(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    r = _clean_returns(returns)
    if r.empty:
        return 0.0
    downside = r.copy()
    downside[downside > 0] = 0
    dd = downside.std(ddof=0)
    if dd == 0:
        return 0.0
    excess = r - (risk_free_rate / periods_per_year)
    return float(excess.mean() / dd * math.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    eq = equity.replace([np.inf, -np.inf], np.nan).dropna()
    if eq.empty:
        return 0.0
    rollmax = eq.cummax()
    dd = (eq / rollmax - 1.0).min()
    return float(dd)


def exposure(positions: pd.Series) -> float:
    if positions is None or len(positions) == 0:
        return 0.0
    mask = positions.abs() > 0
    return float(mask.sum() / len(positions))


def hit_rate(trade_returns: pd.Series) -> float:
    if trade_returns is None or len(trade_returns) == 0:
        return 0.0
    wins = (trade_returns > 0).sum()
    return float(wins / len(trade_returns))
