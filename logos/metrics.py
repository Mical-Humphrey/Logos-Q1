from __future__ import annotations
import math
from math import erf
import numpy as np
import pandas as pd

from .utils.data_hygiene import ensure_no_object_dtype, require_datetime_index

TRADING_DAYS = 252


def _clean_returns(r: pd.Series) -> pd.Series:
    ensure_no_object_dtype(r, context="metrics._clean_returns(returns)")
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if r.std(ddof=0) == 0:
        return pd.Series([], dtype=float)
    return r


def cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    require_datetime_index(equity, context="metrics.cagr(equity)")
    ensure_no_object_dtype(equity, context="metrics.cagr(equity)")
    equity = equity.replace([np.inf, -np.inf], np.nan).dropna()
    if equity.empty:
        return 0.0
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max(len(equity) / periods_per_year, 1e-9)
    return (1 + total_return) ** (1 / years) - 1


def volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    r = _clean_returns(returns)
    require_datetime_index(returns, context="metrics.volatility(returns)")
    if r.empty:
        return 0.0
    return float(r.std(ddof=0) * math.sqrt(periods_per_year))


def sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    require_datetime_index(returns, context="metrics.sharpe(returns)")
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
    require_datetime_index(returns, context="metrics.sortino(returns)")
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
    require_datetime_index(equity, context="metrics.max_drawdown(equity)")
    ensure_no_object_dtype(equity, context="metrics.max_drawdown(equity)")
    eq = equity.replace([np.inf, -np.inf], np.nan).dropna()
    if eq.empty:
        return 0.0
    rollmax = eq.cummax()
    dd = (eq / rollmax - 1.0).min()
    return float(dd)


def exposure(positions: pd.Series) -> float:
    if positions is None or len(positions) == 0:
        return 0.0
    require_datetime_index(positions, context="metrics.exposure(positions)")
    ensure_no_object_dtype(positions, context="metrics.exposure(positions)")
    mask = positions.abs() > 0
    return float(mask.sum() / len(positions))


def hit_rate(trade_returns: pd.Series) -> float:
    if trade_returns is None or len(trade_returns) == 0:
        return 0.0
    wins = (trade_returns > 0).sum()
    return float(wins / len(trade_returns))


def probabilistic_sharpe_ratio(
    returns: pd.Series,
    *,
    benchmark: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Probability that the observed Sharpe ratio exceeds the benchmark."""

    require_datetime_index(
        returns, context="metrics.probabilistic_sharpe_ratio(returns)"
    )
    r = _clean_returns(returns)
    n = len(r)
    if n == 0:
        return 0.0

    sr = sharpe(r, periods_per_year=periods_per_year)
    sample_skew = float(r.skew()) if n > 2 else 0.0
    sample_kurt = float(r.kurtosis()) if n > 3 else 3.0
    denom = 1 - sample_skew * sr + ((sample_kurt - 1.0) / 4.0) * (sr**2)
    if denom <= 0:
        return 0.0

    sigma_sr = math.sqrt(denom / (n - 1)) if n > 1 else 0.0
    if sigma_sr <= 0:
        return 0.0

    z = (sr - benchmark) / sigma_sr
    prob = 0.5 * (1 + erf(z / math.sqrt(2.0)))
    return float(max(0.0, min(1.0, prob)))


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    periods_per_year: int = TRADING_DAYS,
    benchmark: float = 0.0,
    n_trials: int = 1,
) -> float:
    """Deflated Sharpe ratio following Bailey et al. (2014)."""

    require_datetime_index(returns, context="metrics.deflated_sharpe_ratio(returns)")
    r = _clean_returns(returns)
    n = len(r)
    if n <= 1:
        return 0.0

    n_trials = max(int(n_trials), 1)
    sample_skew = float(r.skew()) if n > 2 else 0.0
    sample_kurt = float(r.kurtosis()) if n > 3 else 3.0

    sr = sharpe(r, periods_per_year=periods_per_year)
    sigma_sr = math.sqrt(
        max(1e-12, (1 - sample_skew * sr + ((sample_kurt - 1) / 4.0) * sr**2) / (n - 1))
    )

    if n_trials > 1:
        emax = sigma_sr * math.sqrt(2.0 * math.log(n_trials))
    else:
        emax = 0.0

    adjusted_benchmark = benchmark + emax
    if sigma_sr <= 0:
        return 0.0

    z = (sr - adjusted_benchmark) / sigma_sr
    prob = 0.5 * (1 + erf(z / math.sqrt(2.0)))
    return float(max(0.0, min(1.0, prob)))
