from __future__ import annotations

import numpy as np
import pandas as pd

from logos.strategies.mean_reversion import generate_signals as mr_signals
from logos.strategies.mean_reversion import explain as mr_explain
from logos.strategies.momentum import generate_signals as momo_signals
from logos.strategies.momentum import explain as momo_explain
from logos.strategies.carry import generate_signals as carry_signals
from logos.strategies.carry import explain as carry_explain


def _frame(rows: int = 120, *, scale: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    base = np.linspace(100.0, 120.0, rows)
    close = base + np.sin(np.linspace(0, 8, rows)) * scale
    return pd.DataFrame({"Close": close}, index=idx)


def _assert_payload(payload: dict) -> None:
    assert isinstance(payload["reason"], str)
    assert "signal" in payload
    sig = payload["signal"]
    assert {"value", "timestamp", "price"}.issubset(sig.keys())
    assert "thresholds" in payload and isinstance(payload["thresholds"], dict)
    assert "risk_note" in payload
    assert "params" in payload


def test_mean_reversion_explain_structure() -> None:
    df = _frame(scale=3.0)
    mr_signals(df)
    payload = mr_explain(df)
    _assert_payload(payload)


def test_momentum_explain_structure() -> None:
    df = _frame()
    momo_signals(df)
    payload = momo_explain(df)
    _assert_payload(payload)


def test_carry_explain_structure() -> None:
    df = _frame(scale=0.5)
    carry_signals(df)
    payload = carry_explain(df)
    _assert_payload(payload)
