import numpy as np
import pandas as pd

from logos.backtest.engine import run_backtest


def test_run_backtest_generates_metrics_and_artifacts():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    prices = pd.DataFrame({"Close": [100, 101, 102, 101, 103, 104]}, index=dates)
    signals = pd.Series([0, 1, 1, 0, -1, 0], index=dates)

    result = run_backtest(
        prices=prices, signals=signals, asset_class="equity", periods_per_year=252
    )

    assert set(result.keys()) == {
        "equity_curve",
        "positions",
        "returns",
        "trades",
        "metrics",
    }
    assert len(result["equity_curve"]) == len(prices)
    assert len(result["returns"]) == len(prices)
    assert list(result["trades"].columns) == ["time", "side", "shares", "ref_close"]

    metrics = result["metrics"]
    for key in ["CAGR", "Sharpe", "MaxDD", "WinRate", "Exposure"]:
        assert key in metrics

    assert 0.0 <= metrics["Exposure"] <= 1.0

    flat_signals = pd.Series([0] * len(dates), index=dates)
    flat_result = run_backtest(
        prices=prices, signals=flat_signals, asset_class="equity", periods_per_year=252
    )
    assert flat_result["metrics"]["Sharpe"] == 0.0
    assert flat_result["metrics"]["Exposure"] == 0.0


def test_run_backtest_respects_datetime_labels():
    idx = pd.date_range(
        "2024-01-01 09:30",
        periods=3,
        freq="15min",
        tz="America/New_York",
    )
    closes = [100.0, 101.0, 101.0]
    prices = pd.DataFrame({"Close": closes}, index=idx)
    signals = pd.Series([0, 1, 1], index=idx)

    result = run_backtest(prices=prices, signals=signals, dollar_per_trade=1_000.0)

    expected_qty = int(np.floor(1_000.0 / prices.loc[idx[1], "Close"]))
    positions = result["positions"]
    assert positions.loc[idx[0]] == 0
    assert positions.loc[idx[1]] == expected_qty
    assert positions.loc[idx[2]] == expected_qty

    trades = result["trades"]
    assert not trades.empty
    assert trades.iloc[0]["time"] == idx[1]
