from __future__ import annotations

from pathlib import Path

import pandas as pd

from logos.strategies.mean_reversion import generate_signals as mr_signals
from logos.strategies.momentum import generate_signals as momo_signals
from logos.strategies.carry import generate_signals as carry_signals


def _load_csv(rel_path: str) -> pd.DataFrame:
    root = Path(__file__).resolve().parents[3]
    full_path = root / rel_path
    df = pd.read_csv(full_path, parse_dates=["Date"])  # fixtures share "Date" column
    df = df.set_index("Date").tz_localize("UTC")
    return df


def test_mean_reversion_fixture_emits_trade() -> None:
    df = _load_csv("input_data/raw/MSFT.csv")
    signals = mr_signals(df)
    assert (signals != 0).any()


def test_momentum_fixture_emits_trade() -> None:
    df = _load_csv("input_data/raw/crypto_BTC_USD_1d.csv")
    signals = momo_signals(df)
    assert (signals != 0).any()


def test_carry_fixture_emits_trade() -> None:
    df = _load_csv("input_data/raw/forex_EURUSD_X_1d.csv")
    signals = carry_signals(df)
    assert (signals != 0).any()
