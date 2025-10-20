from __future__ import annotations

import csv
import datetime as dt

import pytest

from logos.live.broker_paper import PaperBrokerAdapter
from logos.live.data_feed import Bar, MemoryBarFeed
from logos.live.order_sizing import SizingConfig
from logos.live.risk import RiskLimits
from logos.live.runner import LiveRunner, LoopConfig
from logos.live.session_manager import create_session
from logos.live.strategy_engine import StrategyOrderGenerator, StrategySpec
from logos.live.time import MockTimeProvider
from logos.logging_setup import detach_handler
from logos import paths as paths_module
from logos.live import session_manager as session_manager_module
from logos.live import runner as runner_module


@pytest.fixture
def patch_live_paths(monkeypatch, tmp_path):
    base = tmp_path / "live"
    sessions = base / "sessions"
    trades = base / "trades"
    reports = base / "reports"
    latest = base / "latest_session"
    paths = {
        "RUNS_LIVE_DIR": base,
        "RUNS_LIVE_SESSIONS_DIR": sessions,
        "RUNS_LIVE_TRADES_DIR": trades,
        "RUNS_LIVE_REPORTS_DIR": reports,
        "RUNS_LIVE_LATEST_LINK": latest,
    }
    for module in (paths_module, session_manager_module):
        for name, value in paths.items():
            monkeypatch.setattr(module, name, value, raising=False)
    monkeypatch.setattr(runner_module, "RUNS_LIVE_TRADES_DIR", trades, raising=False)
    paths_module.ensure_dirs([base, sessions, trades, reports])
    return paths


def test_strategy_order_generator_emits_intents():
    broker = PaperBrokerAdapter(slippage_bps=0.0, fee_bps=0.0)
    spec = StrategySpec(
        symbol="MSFT",
        strategy="momentum",
        params={"fast": 1, "slow": 2},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=2_000.0, max_position=1000.0),
    )
    generator = StrategyOrderGenerator(broker, spec)
    bars = [
        Bar(dt=dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc), open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 31, tzinfo=dt.timezone.utc), open=101, high=102, low=100, close=101, volume=1_100, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 32, tzinfo=dt.timezone.utc), open=102, high=103, low=101, close=103, volume=1_200, symbol="MSFT"),
    ]

    assert generator.process([bars[0]], current_qty=0.0) == []

    second_intents = generator.process([bars[1]], current_qty=0.0)
    assert len(second_intents) == 1
    buy_intent = second_intents[0]
    assert buy_intent.side == "buy"
    assert buy_intent.symbol == "MSFT"
    assert buy_intent.order_type == "market"
    assert pytest.approx(buy_intent.quantity, rel=1e-3) == spec.dollar_per_trade / bars[1].close

    third_intents = generator.process([bars[2]], current_qty=buy_intent.quantity)
    assert len(third_intents) == 1
    sell_intent = third_intents[0]
    assert sell_intent.side == "sell"
    expected_target_qty = spec.dollar_per_trade / bars[2].close
    expected_difference = buy_intent.quantity - expected_target_qty
    assert expected_difference > 0
    assert pytest.approx(sell_intent.quantity, rel=1e-3) == expected_difference


def test_live_runner_generates_trades(tmp_path, monkeypatch, patch_live_paths):
    bars = [
        Bar(dt=dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc), open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 31, tzinfo=dt.timezone.utc), open=101, high=102, low=100, close=101, volume=1_100, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 32, tzinfo=dt.timezone.utc), open=102, high=103, low=101, close=103, volume=1_200, symbol="MSFT"),
        Bar(dt=dt.datetime(2025, 1, 1, 9, 33, tzinfo=dt.timezone.utc), open=104, high=105, low=103, close=104, volume=1_300, symbol="MSFT"),
    ]
    feed = MemoryBarFeed(bars=bars)
    clock = MockTimeProvider(current=dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc))
    broker = PaperBrokerAdapter(time_provider=clock, slippage_bps=0.0, fee_bps=0.0)

    spec = StrategySpec(
        symbol="MSFT",
        strategy="momentum",
        params={"fast": 1, "slow": 2},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=2_000.0, max_position=1000.0),
    )
    generator = StrategyOrderGenerator(broker, spec)
    risk_limits = RiskLimits(max_notional=2_000.0, max_position=1000.0)

    session_paths, handler = create_session("MSFT", "momentum")
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=generator.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock,
            loop_config=LoopConfig(symbol="MSFT", strategy="momentum", interval="1m", max_loops=10),
        )
        runner.run()
    finally:
        detach_handler(handler)

    with session_paths.trades_file.open("r", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) > 1  # header + at least one trade

    daily_path = patch_live_paths["RUNS_LIVE_TRADES_DIR"] / "MSFT_20250101.csv"
    assert daily_path.exists()

    with session_paths.state_file.open("r", encoding="utf-8") as fh:
        state_contents = fh.read()
    assert "equity" in state_contents