from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from logos.live.broker_paper import PaperBrokerAdapter
from logos.strategies.pairs_trading import generate_signals


def _seed_position(
    broker: PaperBrokerAdapter, symbol: str, quantity: float, price: float
) -> None:
    # Access the protected helper to avoid standing up an order book for tests.
    broker._apply_fill(symbol, quantity, price, fees=0.0)  # type: ignore[attr-defined]


def test_portfolio_aggregate_exposure() -> None:
    broker = PaperBrokerAdapter(starting_cash=0.0)
    _seed_position(broker, "MSFT", 15.0, 100.0)
    _seed_position(broker, "AAPL", -5.0, 200.0)
    total_exposure = sum(abs(pos.quantity) for pos in broker.get_positions())
    assert total_exposure == pytest.approx(20.0)


def test_portfolio_trade_isolation_per_symbol() -> None:
    broker = PaperBrokerAdapter(starting_cash=0.0)
    _seed_position(broker, "MSFT", 10.0, 100.0)
    _seed_position(broker, "AAPL", -7.0, 150.0)
    quantities = {pos.symbol: pos.quantity for pos in broker.get_positions()}
    assert quantities["MSFT"] == pytest.approx(10.0)
    assert quantities["AAPL"] == pytest.approx(-7.0)


def test_pairs_trading_stays_balanced_when_series_identical() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")
    base = np.linspace(100.0, 110.0, len(idx))
    df = pd.DataFrame({"LEG_A": base, "LEG_B": base}, index=idx)
    signals = generate_signals(
        df, symA="LEG_A", symB="LEG_B", lookback=20, z_entry=1.0, z_exit=0.5
    )
    assert set(signals.unique()) <= {0, 1}
    assert signals.iloc[-1] == 0


def test_pairs_trading_flags_divergence() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")
    leg_a = np.concatenate(
        [np.linspace(100.0, 101.0, 55), np.array([120.0, 121.0, 122.0, 123.0, 124.0])]
    )
    leg_b = np.linspace(100.0, 101.0, len(idx))
    df = pd.DataFrame({"LEG_A": leg_a, "LEG_B": leg_b}, index=idx)
    signals = generate_signals(
        df, symA="LEG_A", symB="LEG_B", lookback=30, z_entry=1.5, z_exit=0.5
    )
    assert signals.iloc[-1] == -1
