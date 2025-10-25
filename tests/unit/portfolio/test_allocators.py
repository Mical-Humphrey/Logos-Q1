import numpy as np
import pandas as pd
import pytest

from logos.portfolio.allocators import (
    AllocatorConfig,
    risk_budget_allocation,
    volatility_parity_allocation,
)


def _build_returns(columns: list[str], values: list[list[float]]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="D")
    return pd.DataFrame(values, index=idx, columns=columns)


def test_volatility_parity_equal_volatility_allocates_evenly():
    returns = _build_returns(
        ["A", "B", "C"],
        [[0.01, 0.01, 0.01]] * 30,
    )
    weights = volatility_parity_allocation(returns, AllocatorConfig(vol_lookback_days=30))
    assert weights.index.tolist() == ["A", "B", "C"]
    assert np.allclose(weights.to_numpy(), np.full(3, 1 / 3), atol=1e-6)


def test_volatility_parity_downweights_high_variance_asset():
    series = [
        [0.005, 0.015],
        [0.004, -0.020],
        [0.006, 0.018],
        [0.005, -0.019],
    ]
    returns = _build_returns(["low", "high"], series * 10)
    weights = volatility_parity_allocation(
        returns,
        AllocatorConfig(vol_lookback_days=40, corr_shrink=0.0),
    )
    assert weights.loc["low"] > weights.loc["high"]
    assert pytest.approx(weights.sum(), rel=1e-6) == 1.0


def test_risk_budget_allocation_returns_normalized_weights():
    pattern = np.array(
        [
            [0.01, 0.0, 0.0],
            [0.0, 0.02, 0.0],
            [0.0, 0.0, -0.015],
            [-0.01, 0.0, 0.0],
            [0.0, -0.02, 0.0],
            [0.0, 0.0, 0.015],
        ]
    )
    returns = _build_returns(["X", "Y", "Z"], np.tile(pattern, (10, 1)))
    weights = risk_budget_allocation(
        returns,
        budgets=pd.Series({"X": 0.6, "Y": 0.3, "Z": 0.1}),
        config=AllocatorConfig(vol_lookback_days=60, corr_shrink=0.0, ewma_decay=0.5),
    )
    assert weights.index.tolist() == ["X", "Y", "Z"]
    assert pytest.approx(weights.sum(), rel=1e-6) == 1.0
    assert (weights >= 0.0).all()


def test_risk_budget_allocation_handles_zero_budgets_with_fallback():
    returns = _build_returns(
        ["solo"],
        [[0.002]] * 20,
    )
    weights = risk_budget_allocation(
        returns,
        budgets=pd.Series({"solo": 0.0}),
        config=AllocatorConfig(vol_lookback_days=20),
    )
    assert pytest.approx(weights.iloc[0], rel=1e-6) == 1.0


def test_ewma_raises_on_empty_frame():
    with pytest.raises(ValueError):
        volatility_parity_allocation(pd.DataFrame(), AllocatorConfig())
