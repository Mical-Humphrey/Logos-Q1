from __future__ import annotations

import pandas as pd

from logos.backtest.engine import run_backtest
from logos.live.risk import RiskLimits


def _price_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    close = [100.0, 101.0, 102.0, 103.0, 104.0]
    volume = [1_000.0] * len(idx)
    return pd.DataFrame({"Close": close, "Volume": volume}, index=idx)


def _signals(entries: list[int]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(entries), freq="D")
    return pd.Series(entries, index=idx, name="signals")


def test_run_backtest_blocks_orders_exceeding_per_trade_cap():
    prices = _price_frame()
    signals = _signals([0, 1, 1, 0, 0])
    limits = RiskLimits(per_trade_risk_cap=0.05, stale_data_threshold_s=0.0)

    result = run_backtest(
        prices=prices,
        signals=signals,
        dollar_per_trade=50_000.0,
        risk_limits=limits,
        portfolio_nav=100_000.0,
        strategy_id="demo",
        symbol="MSFT",
    )

    assert result["trades"].empty
    assert (result["positions"] == 0.0).all()
    assert (result["equity_curve"] == 100_000.0).all()


def test_run_backtest_respects_capacity_block():
    prices = _price_frame()
    signals = _signals([0, 1, 0, 0, 0])
    limits = RiskLimits(
        per_trade_risk_cap=1.0,
        capacity_max_participation=0.10,
        capacity_warn_participation=0.05,
        stale_data_threshold_s=0.0,
    )

    result = run_backtest(
        prices=prices,
        signals=signals,
        dollar_per_trade=200_000.0,
        risk_limits=limits,
        portfolio_nav=1_000_000.0,
        strategy_id="demo",
        symbol="BTC-USD",
    )

    assert result["trades"].empty
    assert (result["positions"] == 0.0).all()


def test_run_backtest_allows_orders_within_limits():
    prices = _price_frame()
    signals = _signals([0, 1, 1, 0, 0])
    limits = RiskLimits(
        per_trade_risk_cap=0.25,
        portfolio_gross_cap=0.75,
        per_asset_cap=0.75,
        capacity_max_participation=0.0,
        stale_data_threshold_s=0.0,
    )

    result = run_backtest(
        prices=prices,
        signals=signals,
        dollar_per_trade=10_000.0,
        risk_limits=limits,
        portfolio_nav=100_000.0,
        strategy_id="demo",
        symbol="AAPL",
    )

    trades = result["trades"]
    assert len(trades) == 2
    assert trades.iloc[0]["side"] == 1
    assert trades.iloc[1]["side"] == -1
    assert abs(result["positions"].iloc[-1]) <= 2.0
