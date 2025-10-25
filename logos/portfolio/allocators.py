from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = [
    "AllocatorConfig",
    "ewma_covariance",
    "volatility_parity_allocation",
    "risk_budget_allocation",
]


@dataclass(slots=True)
class AllocatorConfig:
    """Configuration defaults for portfolio allocators."""

    vol_lookback_days: int = 20
    ewma_decay: float = 0.94
    corr_shrink: float = 0.5
    target_vol_annual: float = 0.10
    rebalance_drift: float = 0.20


def _validate_returns(returns: pd.DataFrame) -> pd.DataFrame:
    if returns.empty:
        raise ValueError("returns frame is empty")
    clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if clean.columns.hasnans:
        raise ValueError("returns columns must be named")
    return clean.astype(float)


def ewma_covariance(returns: pd.DataFrame, decay: float = 0.94) -> pd.DataFrame:
    """Exponentially weighted covariance estimate using decay \in (0, 1)."""

    if not 0.0 < decay < 1.0:
        raise ValueError("decay must be in (0, 1)")
    frame = _validate_returns(returns)
    n_assets = frame.shape[1]
    cov = np.zeros((n_assets, n_assets), dtype=float)
    weight = 0.0
    for row in frame.to_numpy():
        cov = decay * cov + (1.0 - decay) * np.outer(row, row)
        weight = decay * weight + (1.0 - decay)
    if weight <= 0.0:
        raise ValueError("invalid weight accumulation for EWMA covariance")
    cov /= weight
    return pd.DataFrame(cov, index=frame.columns, columns=frame.columns)


def _shrink_covariance(cov: pd.DataFrame, shrink: float) -> pd.DataFrame:
    shrink = max(0.0, min(1.0, shrink))
    if shrink == 0.0:
        return cov
    diag = np.diag(np.diag(cov.to_numpy()))
    shrunk = (1.0 - shrink) * cov.to_numpy() + shrink * diag
    return pd.DataFrame(shrunk, index=cov.index, columns=cov.columns)


def _normalize(weights: np.ndarray) -> np.ndarray:
    total = float(np.sum(weights))
    if total <= 0.0:
        return np.full_like(weights, 1.0 / weights.size)
    return weights / total


def volatility_parity_allocation(
    returns: pd.DataFrame,
    config: AllocatorConfig | None = None,
) -> pd.Series:
    """Compute inverse-volatility weights with optional covariance shrinkage."""

    cfg = config or AllocatorConfig()
    tail = returns.tail(cfg.vol_lookback_days)
    cov = ewma_covariance(tail, cfg.ewma_decay)
    shrunk = _shrink_covariance(cov, cfg.corr_shrink)
    variances = np.diag(shrunk.to_numpy())
    if np.any(variances <= 1e-12):
        weights = np.full(len(variances), 1.0 / len(variances))
    else:
        inv_vol = 1.0 / np.sqrt(variances)
        weights = _normalize(inv_vol)
    return pd.Series(weights, index=shrunk.index, name="vol_parity")


def _risk_contributions(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    portfolio_var = float(weights.T @ cov @ weights)
    if portfolio_var <= 0.0:
        return np.zeros_like(weights)
    portfolio_vol = math.sqrt(portfolio_var)
    marginal = cov @ weights
    contributions = weights * marginal / portfolio_vol
    total = float(np.sum(contributions))
    if total <= 0.0:
        return np.zeros_like(weights)
    return contributions / total


def risk_budget_allocation(
    returns: pd.DataFrame,
    budgets: pd.Series | pd.DataFrame | dict[str, float],
    config: AllocatorConfig | None = None,
    *,
    max_iter: int = 500,
    tol: float = 1e-6,
) -> pd.Series:
    """Iterative risk parity allocation matching target risk budgets."""

    cfg = config or AllocatorConfig()
    frame = returns.tail(cfg.vol_lookback_days)
    cov = ewma_covariance(frame, cfg.ewma_decay)
    shrunk = _shrink_covariance(cov, cfg.corr_shrink)
    if isinstance(budgets, pd.DataFrame):
        budgets = budgets.iloc[-1]
    if isinstance(budgets, dict):
        budgets = pd.Series(budgets, dtype=float)
    if not isinstance(budgets, pd.Series):
        raise TypeError("budgets must be Series or mapping")
    aligned = budgets.reindex(shrunk.index).fillna(1.0)
    target = aligned.to_numpy(dtype=float)
    target = np.where(target < 0.0, 0.0, target)
    if np.allclose(target, 0.0):
        target = np.full_like(target, 1.0 / target.size)
    target = _normalize(target)
    n = len(target)
    weights = np.full(n, 1.0 / n)
    cov_values = shrunk.to_numpy()
    for _ in range(max_iter):
        contributions = _risk_contributions(weights, cov_values)
        if np.linalg.norm(contributions - target, ord=1) < tol:
            break
        adjustment = target / np.maximum(contributions, 1e-12)
        weights *= adjustment
        weights = np.maximum(weights, 1e-12)
        weights = _normalize(weights)
    return pd.Series(weights, index=shrunk.index, name="risk_budget")
