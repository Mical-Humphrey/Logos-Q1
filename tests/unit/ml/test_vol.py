from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from logos.ml.vol import VolatilityAdvisor


def _make_price_series() -> pd.Series:
    index = pd.date_range("2024-01-01", periods=250, freq="B")
    base = 100 + np.cumsum(0.2 + 0.5 * np.sin(np.linspace(0, 12, 250)))
    return pd.Series(base, index=index)


def test_volatility_forecast_produces_envelope() -> None:
    advisor = VolatilityAdvisor(halflife=30, horizon_days=5, band_width=1.2)
    envelope = advisor.forecast(_make_price_series())

    assert envelope.forecast > 0
    assert envelope.lower <= envelope.upper
    assert 0 <= envelope.confidence <= 1
    assert envelope.metadata is not None


def test_volatility_promotion_requires_identifier() -> None:
    advisor = VolatilityAdvisor()
    envelope = advisor.forecast(_make_price_series())
    with pytest.raises(ValueError):
        VolatilityAdvisor.promote(envelope, approved_by="")

    promoted = VolatilityAdvisor.promote(envelope, approved_by="risk")
    assert promoted.metadata is not None
    assert promoted.metadata["approved_by"] == "risk"
