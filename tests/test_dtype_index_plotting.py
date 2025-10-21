from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from typing import cast

from logos.backtest.engine import run_backtest
from logos.cli import _plot_equity
from logos.live.data_feed import Bar
from logos.live.broker_base import BrokerAdapter
from logos.live.strategy_engine import StrategyOrderGenerator, StrategySpec
from logos.metrics import cagr


def test_run_backtest_requires_datetime_index() -> None:
    prices = pd.DataFrame({"Close": [100.0, 101.0]}, index=[0, 1])
    signals = pd.Series([0, 1], index=[0, 1])

    with pytest.raises(
        ValueError, match=r"run_backtest\(prices\) requires a pandas.DatetimeIndex"
    ):
        run_backtest(prices=prices, signals=signals)


def test_run_backtest_rejects_object_dtype_prices() -> None:
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    prices = pd.DataFrame({"Close": ["100", "101"]}, index=idx)
    signals = pd.Series([0, 1], index=idx)

    with pytest.raises(
        ValueError, match=r"run_backtest\(prices\) must not contain object dtype"
    ):
        run_backtest(prices=prices, signals=signals)


def test_metrics_require_datetime_index() -> None:
    series = pd.Series([100.0, 101.0], index=[0, 1])
    with pytest.raises(
        ValueError, match=r"metrics.cagr\(equity\) requires a pandas.DatetimeIndex"
    ):
        cagr(series)


def test_plot_equity_to_numpy_conversion() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    equity = pd.Series([1.0, 1.5, 2.0], index=idx)

    fig = _plot_equity(equity)
    try:
        ax = fig.axes[0]
        line = ax.lines[0]
        y_data = line.get_ydata()
        assert hasattr(y_data, "dtype")
        assert y_data.dtype == float
    finally:
        plt.close(fig)


def test_strategy_engine_validates_frame(monkeypatch) -> None:
    class DummyBroker:
        def get_symbol_meta(self, symbol: str):
            from logos.live.broker_base import SymbolMeta

            return SymbolMeta(symbol=symbol)

    spec = StrategySpec(symbol="MSFT", strategy="mean_reversion")
    dummy_broker = cast(BrokerAdapter, DummyBroker())
    generator = StrategyOrderGenerator(dummy_broker, spec)

    import logos.live.strategy_engine as engine_module

    original_require = engine_module.require_datetime_index

    def fake_require(obj, *, context: str) -> None:
        obj["Close"] = obj["Close"].astype("object")
        original_require(obj, context=context)

    monkeypatch.setattr(engine_module, "require_datetime_index", fake_require)

    bars = [
        Bar(
            dt=pd.Timestamp("2024-01-01 09:30", tz="UTC"),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1_000.0,
            symbol="MSFT",
        )
    ]

    with pytest.raises(
        ValueError,
        match=r"StrategyOrderGenerator\.process\(frame\) must not contain object dtype",
    ):
        generator.process(bars, current_qty=0.0)
