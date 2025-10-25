from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from logos.ml.regime import RegimeAdvisor, classify_regime


def test_regime_detects_trend_and_confidence() -> None:
    index = pd.date_range("2024-01-01", periods=200, freq="B")
    trend = np.linspace(0, 20, 200)
    noise = 0.2 * np.sin(np.linspace(0, 6, 200))
    prices = pd.Series(100 + trend + noise, index=index)

    report = classify_regime(
        prices,
        trend_lookback=60,
        vol_lookback=20,
        trend_threshold=0.2,
        vol_threshold=1.5,
    )

    assert report.trend_state == "bull"
    assert 0 <= report.confidence <= 1
    assert report.metadata["trend_lookback"] == 60.0


def test_regime_promotion_requires_approval() -> None:
    index = pd.date_range("2024-01-01", periods=150, freq="B")
    prices = pd.Series(100 + np.linspace(-10, 10, 150), index=index)
    advisor = RegimeAdvisor(trend_threshold=0.1, vol_threshold=1.2)
    report = advisor.analyze(prices)

    with pytest.raises(ValueError):
        RegimeAdvisor.promote(report, approved_by="")

    promoted = RegimeAdvisor.promote(report, approved_by="risk-committee")
    assert promoted.promoted is True
    assert promoted.approved_by == "risk-committee"
