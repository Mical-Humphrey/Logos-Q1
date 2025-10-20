import numpy as np
import pandas as pd
from logos.metrics import sharpe, sortino, cagr, max_drawdown, volatility


def test_metrics_stability():
    np.random.seed(0)
    r = pd.Series(np.random.normal(0.001, 0.01, 252))
    eq = (1 + r).cumprod()
    assert volatility(r) >= 0
    assert sharpe(r) == sharpe(r)  # not NaN
    assert sortino(r) == sortino(r)
    assert -1.0 <= max_drawdown(eq) <= 0.0
    assert -1.0 < cagr(eq) < 1.0


def test_zero_variance_returns():
    r = pd.Series([0.0] * 100)
    eq = (1 + r).cumprod()
    assert sharpe(r) == 0.0
    assert sortino(r) == 0.0
    assert cagr(eq) == 0.0
