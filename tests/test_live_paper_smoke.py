from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

from logos.live import runner as runner_module
from logos import paths as paths_module
from logos.live import session_manager as session_manager_module
from logos.live.artifacts import load_account, load_orders, load_positions, load_trades
from logos.live.broker_paper import PaperBrokerAdapter
from logos.live.data_feed import CsvBarFeed
from logos.live.order_sizing import SizingConfig
from logos.live.risk import RiskLimits
from logos.live.runner import LiveRunner, LoopConfig
from logos.live.session_manager import create_session
from logos.live.strategy_engine import StrategyOrderGenerator, StrategySpec
from logos.live.time import MockTimeProvider
from logos.logging_setup import detach_handler


def _patch_live_paths(monkeypatch, base: Path) -> None:
    sessions = base / "sessions"
    trades = base / "trades"
    reports = base / "reports"
    latest = base / "latest_session"
    mapping = {
        "RUNS_LIVE_DIR": base,
        "RUNS_LIVE_SESSIONS_DIR": sessions,
        "RUNS_LIVE_TRADES_DIR": trades,
        "RUNS_LIVE_REPORTS_DIR": reports,
        "RUNS_LIVE_LATEST_LINK": latest,
    }
    for module in (paths_module, session_manager_module):
        for name, value in mapping.items():
            monkeypatch.setattr(module, name, value, raising=False)
    monkeypatch.setattr(runner_module, "RUNS_LIVE_TRADES_DIR", trades, raising=False)
    paths_module.ensure_dirs([base, sessions, trades, reports])


def _write_feed(path: Path, bars: list[tuple[dt.datetime, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["dt", "open", "high", "low", "close", "volume", "symbol"])
        for bar_dt, price in bars:
            writer.writerow(
                [
                    bar_dt.isoformat(),
                    price,
                    price + 0.5,
                    price - 0.5,
                    price,
                    1_000,
                    "MSFT",
                ]
            )


def test_live_paper_smoke(tmp_path, monkeypatch):
    base = tmp_path / "live"
    _patch_live_paths(monkeypatch, base)

    feed_path = tmp_path / "feed.csv"
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [
        (start, 100.0),
        (start + dt.timedelta(minutes=1), 101.0),
        (start + dt.timedelta(minutes=2), 102.0),
        (start + dt.timedelta(minutes=3), 103.0),
    ]
    _write_feed(feed_path, bars)

    clock = MockTimeProvider(current=start)
    broker = PaperBrokerAdapter(time_provider=clock, slippage_bps=0.0, fee_bps=0.0)
    feed = CsvBarFeed(path=feed_path, time_provider=clock)
    strategy_spec = StrategySpec(
        symbol="MSFT",
        strategy="momentum",
        params={"fast": 1, "slow": 2},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=50_000.0, max_position=10_000.0),
    )
    order_generator = StrategyOrderGenerator(broker, strategy_spec)
    risk_limits = RiskLimits(max_drawdown_bps=5_000.0)

    session_paths, handler = create_session("MSFT", "momentum", when=start)
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=order_generator.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock,
            loop_config=LoopConfig(
                symbol="MSFT", strategy="momentum", interval="1m", max_loops=10
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    orders_df = load_orders(session_paths.orders_file)
    trades_df = load_trades(session_paths.trades_file)
    positions_df = load_positions(session_paths.positions_file)
    account_df = load_account(session_paths.account_file, symbol="MSFT")

    for df in (orders_df, trades_df, positions_df, account_df):
        assert not df.empty
        assert isinstance(df.iloc[0]["ts"], pd.Timestamp)
