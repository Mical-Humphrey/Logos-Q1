from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from logos.strategy import StrategyError
from logos.strategies.mean_reversion import MeanReversionPreset
from logos.strategies.momentum import MomentumPreset
from logos.strategies.carry import CarryPreset


def _frame(rows: int) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    close = np.linspace(100.0, 101.0, rows)
    return pd.DataFrame({"Close": close}, index=idx)


def test_mean_reversion_window_guard() -> None:
    with pytest.raises(StrategyError):
        MeanReversionPreset(lookback=1)


def test_momentum_window_relation_guard() -> None:
    with pytest.raises(StrategyError):
        MomentumPreset(fast=30, slow=20)


def test_carry_insufficient_data_fails_closed() -> None:
    preset = CarryPreset(lookback=5)
    df = _frame(rows=4)
    preset.fit(df)
    with pytest.raises(StrategyError):
        preset.predict(df)


def test_mean_reversion_nan_inputs_fail_closed() -> None:
    preset = MeanReversionPreset(lookback=5)
    df = _frame(rows=10)
    df.loc[df.index[-1], "Close"] = np.nan
    with pytest.raises(StrategyError):
        preset.fit(df)
