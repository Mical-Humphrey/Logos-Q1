from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from typing import Any, Dict, Mapping, cast

from logos.strategy import StrategyContext, StrategyError, StrategyPreset, guard_no_nan


class DummyPreset(StrategyPreset):
    name = "dummy"

    def __init__(self, *, exposure_cap: float = 1.0) -> None:
        super().__init__(exposure_cap=exposure_cap)
        self._pending: (
            tuple[pd.Timestamp, float, Dict[str, float | int | str | None]] | None
        ) = None

    def fit(self, df: pd.DataFrame) -> None:  # type: ignore[override]
        super().fit(df)

    def predict(self, df: pd.DataFrame) -> pd.Series:  # type: ignore[override]
        self._require_fit()
        assert not df.empty
        signals = pd.Series(np.linspace(-2, 2, len(df)), index=df.index, dtype=float)
        ts = df.index[-1]
        price = float(df["Close"].iloc[-1])
        diagnostics: Dict[str, float | int | str | None] = {"sentinel": 1}
        self._pending = (ts, price, diagnostics)
        return signals

    def generate_order_intents(self, signals: pd.Series) -> pd.Series:  # type: ignore[override]
        clipped = super().generate_order_intents(signals)
        if self._pending and not clipped.empty:
            ts, price, diagnostics = self._pending
            ctx = StrategyContext(
                timestamp=ts,
                price=price,
                signal=float(clipped.iloc[-1]),
                diagnostics=diagnostics,
            )
            self._record_context(ctx)
        self._pending = None
        return clipped


def _build_frame(rows: int = 10) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    data = {
        "Close": np.linspace(100.0, 110.0, rows),
    }
    return pd.DataFrame(data, index=idx)


def test_predict_requires_fit() -> None:
    preset = DummyPreset()
    df = _build_frame()
    with pytest.raises(StrategyError):
        preset.predict(df)


def test_generate_order_intents_clamps_and_records_context() -> None:
    preset = DummyPreset(exposure_cap=0.5)
    df = _build_frame()
    preset.fit(df)
    raw = preset.predict(df)
    clipped = preset.generate_order_intents(raw)
    assert clipped.max() <= 0.5
    assert clipped.min() >= -0.5
    explain = cast(Dict[str, Any], preset.explain())
    signal_section = cast(Mapping[str, Any], explain["signal"])
    assert signal_section["value"] == pytest.approx(clipped.iloc[-1])
    diagnostics_section = cast(Mapping[str, Any], explain.get("diagnostics", {}))
    assert "sentinel" in diagnostics_section


def test_generate_order_intents_rejects_nans() -> None:
    preset = DummyPreset()
    nan_series = pd.Series([0.0, math.nan], index=[0, 1], dtype=float)
    guard_no_nan(pd.Series([0.0, 1.0], dtype=float), context="ok")
    with pytest.raises(StrategyError):
        preset.generate_order_intents(nan_series)
