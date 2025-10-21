from __future__ import annotations

import csv
import datetime as dt
import json
from typing import Iterable, List

import pytest

from logos.live.broker_base import OrderIntent
from logos.live.broker_paper import PaperBrokerAdapter
from logos.live.data_feed import Bar, MemoryBarFeed
from logos.live.artifacts import load_account, load_orders, load_positions, load_trades
from logos.live.order_sizing import SizingConfig
from logos.live.risk import RiskLimits
from logos.live.runner import LiveRunner, LoopConfig
from logos.live.session_manager import create_session
from logos.live.strategy_engine import StrategyOrderGenerator, StrategySpec
from logos.live.time import MockTimeProvider
from logos.logging_setup import attach_run_file_handler, detach_handler
from logos import paths as paths_module
from logos.live import session_manager as session_manager_module
from logos.live import runner as runner_module
from logos.window import Window


class SequencedTimeProvider:
    """Return a predetermined sequence of timestamps, holding the final value."""

    def __init__(self, timestamps: Iterable[dt.datetime]) -> None:
        self._timestamps: List[dt.datetime] = list(timestamps)
        if not self._timestamps:
            raise ValueError("timestamps must not be empty")
        self._index = 0

    def utc_now(self) -> dt.datetime:
        if self._index < len(self._timestamps):
            value = self._timestamps[self._index]
            self._index += 1
        else:
            value = self._timestamps[-1]
        return value


def _day_window(anchor: dt.datetime) -> Window:
    end = anchor + dt.timedelta(days=1)
    return Window.from_bounds(start=anchor.date(), end=end.date())


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
        Bar(
            dt=dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1_000,
            symbol="MSFT",
        ),
        Bar(
            dt=dt.datetime(2025, 1, 1, 9, 31, tzinfo=dt.timezone.utc),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1_100,
            symbol="MSFT",
        ),
        Bar(
            dt=dt.datetime(2025, 1, 1, 9, 32, tzinfo=dt.timezone.utc),
            open=102,
            high=103,
            low=101,
            close=103,
            volume=1_200,
            symbol="MSFT",
        ),
    ]

    assert generator.process([bars[0]], current_qty=0.0) == []

    second_intents = generator.process([bars[1]], current_qty=0.0)
    assert len(second_intents) == 1
    buy_intent = second_intents[0]
    assert buy_intent.side == "buy"
    assert buy_intent.symbol == "MSFT"
    assert buy_intent.order_type == "market"
    assert (
        pytest.approx(buy_intent.quantity, rel=1e-3)
        == spec.dollar_per_trade / bars[1].close
    )

    third_intents = generator.process([bars[2]], current_qty=buy_intent.quantity)
    assert len(third_intents) == 1
    sell_intent = third_intents[0]
    assert sell_intent.side == "sell"
    expected_target_qty = spec.dollar_per_trade / bars[2].close
    expected_difference = buy_intent.quantity - expected_target_qty
    assert expected_difference > 0
    assert pytest.approx(sell_intent.quantity, rel=1e-3) == expected_difference


def test_live_runner_generates_trades(tmp_path, monkeypatch, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [
        Bar(
            dt=start,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1_000,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=1),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1_100,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=2),
            open=102,
            high=103,
            low=101,
            close=103,
            volume=1_200,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=3),
            open=104,
            high=105,
            low=103,
            close=104,
            volume=1_300,
            symbol="MSFT",
        ),
    ]
    feed = MemoryBarFeed(bars=bars)
    clock = MockTimeProvider(current=start)
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
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=10,
            ),
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


def test_live_runner_halts_on_kill_switch(tmp_path, monkeypatch, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [
        Bar(
            dt=start,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1_000,
            symbol="MSFT",
        ),
    ]
    feed = MemoryBarFeed(bars=bars)
    clock = MockTimeProvider(current=start)
    broker = PaperBrokerAdapter(time_provider=clock, slippage_bps=0.0, fee_bps=0.0)

    spec = StrategySpec(
        symbol="MSFT",
        strategy="momentum",
        params={"fast": 1, "slow": 2},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=2_000.0, max_position=1000.0),
    )
    generator = StrategyOrderGenerator(broker, spec)
    kill_switch = tmp_path / "kill_switch.flag"
    kill_switch.write_text("halt", encoding="utf-8")
    risk_limits = RiskLimits(
        max_notional=2_000.0,
        max_position=1000.0,
        kill_switch_file=kill_switch,
        stale_data_threshold_s=60,
    )

    session_paths, handler = create_session("MSFT", "momentum")
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=generator.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=5,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    with session_paths.trades_file.open("r", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 2  # comment + header, no trades recorded

    with session_paths.state_events_file.open("r", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    assert any(
        event.get("type") == "circuit_breaker"
        and event.get("reason") == "kill_switch_triggered"
        for event in events
    )


def test_live_runner_emits_stale_data_event(tmp_path, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    provider = SequencedTimeProvider(
        [
            start,
            start,
            start,
            start + dt.timedelta(minutes=5),
            start + dt.timedelta(minutes=5),
            start + dt.timedelta(minutes=5),
        ]
    )
    feed = MemoryBarFeed(
        bars=[
            Bar(
                dt=start,
                open=100,
                high=100,
                low=100,
                close=100,
                volume=1_000,
                symbol="MSFT",
            )
        ]
    )
    broker = PaperBrokerAdapter(time_provider=provider, slippage_bps=0.0, fee_bps=0.0)
    session_paths, handler = create_session("MSFT", "momentum")
    risk_limits = RiskLimits(
        max_notional=0.0, max_position=0.0, stale_data_threshold_s=60
    )
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=lambda bars, current_qty: [],
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=provider,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=5,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    with session_paths.state_events_file.open("r", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]

    assert any(
        event.get("type") == "circuit_breaker" and event.get("reason") == "data_stale"
        for event in events
    )


def test_live_runner_persists_and_recovers_state(tmp_path, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    initial_bars = [
        Bar(
            dt=start, open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"
        ),
        Bar(
            dt=start + dt.timedelta(minutes=1),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1_100,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=2),
            open=102,
            high=103,
            low=101,
            close=102,
            volume=1_050,
            symbol="MSFT",
        ),
    ]
    feed_initial = MemoryBarFeed(bars=initial_bars)
    clock_initial = MockTimeProvider(current=start)
    broker_initial = PaperBrokerAdapter(
        time_provider=clock_initial, slippage_bps=0.0, fee_bps=0.0
    )
    spec = StrategySpec(
        symbol="MSFT",
        strategy="momentum",
        params={"fast": 1, "slow": 2},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=2_000.0, max_position=1000.0),
    )
    generator_initial = StrategyOrderGenerator(broker_initial, spec)
    risk_limits = RiskLimits(max_notional=2_000.0, max_position=1000.0)

    session_paths, handler = create_session("MSFT", "momentum")
    try:
        runner = LiveRunner(
            broker=broker_initial,
            feed=feed_initial,
            order_generator=generator_initial.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock_initial,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=5,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    state_after_first = json.loads(session_paths.state_file.read_text(encoding="utf-8"))
    assert "MSFT" in state_after_first["positions"]
    initial_qty = state_after_first["positions"]["MSFT"]["qty"]
    assert initial_qty > 0

    followup_bars = [
        Bar(
            dt=start + dt.timedelta(minutes=3),
            open=103,
            high=104,
            low=102,
            close=103,
            volume=1_200,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=4),
            open=104,
            high=105,
            low=103,
            close=104,
            volume=1_250,
            symbol="MSFT",
        ),
    ]
    feed_followup = MemoryBarFeed(bars=followup_bars)
    clock_followup = MockTimeProvider(current=start + dt.timedelta(minutes=3))
    broker_followup = PaperBrokerAdapter(
        time_provider=clock_followup, slippage_bps=0.0, fee_bps=0.0
    )
    generator_followup = StrategyOrderGenerator(broker_followup, spec)

    handler_followup = attach_run_file_handler(session_paths.logs_dir / "run.log")
    try:
        runner = LiveRunner(
            broker=broker_followup,
            feed=feed_followup,
            order_generator=generator_followup.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock_followup,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=5,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler_followup)

    state_after_second = json.loads(
        session_paths.state_file.read_text(encoding="utf-8")
    )
    assert state_after_second["last_bar_iso"] == followup_bars[-1].dt.isoformat()
    assert "MSFT" in state_after_second["positions"]
    final_qty = state_after_second["positions"]["MSFT"]["qty"]
    assert final_qty >= 0
    assert final_qty <= initial_qty + 1e-6
    assert state_after_second["realized_pnl"] >= 0

    with session_paths.state_events_file.open("r", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    assert any(event.get("type") == "state" for event in events)

    orders_df = load_orders(
        session_paths.orders_file,
        session_id=session_paths.session_id,
        strategy="momentum",
    )
    trades_df = load_trades(
        session_paths.trades_file,
        session_id=session_paths.session_id,
        strategy="momentum",
    )
    positions_df = load_positions(
        session_paths.positions_file,
        session_id=session_paths.session_id,
        strategy="momentum",
    )
    account_df = load_account(
        session_paths.account_file,
        session_id=session_paths.session_id,
        strategy="momentum",
        symbol="MSFT",
    )

    assert not orders_df.empty
    assert not trades_df.empty
    assert not positions_df.empty
    assert not account_df.empty
    assert orders_df["session_id"].iloc[0] == session_paths.session_id
    assert trades_df["strategy"].iloc[0] == "momentum"
    assert set(positions_df["symbol"]) == {"MSFT"}
    assert account_df["symbol"].iloc[-1] == "MSFT"

    summary_text = session_paths.session_report.read_text(encoding="utf-8").strip()
    summary_lines = summary_text.splitlines()
    assert summary_lines[0] == f"# Session {session_paths.session_id}"
    assert any(line.startswith("- Halt Reason:") for line in summary_lines)
    assert any(line.startswith("- Window:") for line in summary_lines)


def test_live_runner_drawdown_breaker(tmp_path, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [
        Bar(
            dt=start, open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"
        ),
        Bar(
            dt=start + dt.timedelta(minutes=1),
            open=120,
            high=121,
            low=119,
            close=120,
            volume=1_050,
            symbol="MSFT",
        ),
        Bar(
            dt=start + dt.timedelta(minutes=2),
            open=80,
            high=81,
            low=79,
            close=80,
            volume=1_200,
            symbol="MSFT",
        ),
    ]
    feed = MemoryBarFeed(bars=bars)
    clock = MockTimeProvider(current=start)
    broker = PaperBrokerAdapter(
        time_provider=clock, starting_cash=1_000.0, slippage_bps=0.0, fee_bps=0.0
    )

    class SingleLongGenerator:
        def __init__(self) -> None:
            self.submitted = False

        def __call__(self, bars, current_qty):
            if self.submitted:
                return []
            self.submitted = True
            if current_qty >= 5.0:
                return []
            return [OrderIntent(symbol="MSFT", side="buy", quantity=5.0)]

    order_generator = SingleLongGenerator()
    risk_limits = RiskLimits(
        max_notional=50_000.0, max_position=1_000.0, max_drawdown_bps=1_000
    )

    session_paths, handler = create_session("MSFT", "momentum")
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=order_generator,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=10,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    with session_paths.state_events_file.open("r", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    assert any(
        event.get("reason") == "session_drawdown_limit"
        for event in events
        if event.get("type") == "circuit_breaker"
    )


def test_live_runner_consecutive_reject_breaker(tmp_path, patch_live_paths):
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [
        Bar(
            dt=start, open=100, high=101, low=99, close=100, volume=1_000, symbol="MSFT"
        ),
        Bar(
            dt=start + dt.timedelta(minutes=1),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1_100,
            symbol="MSFT",
        ),
    ]
    feed = MemoryBarFeed(bars=bars)
    clock = MockTimeProvider(current=start)
    broker = PaperBrokerAdapter(time_provider=clock, slippage_bps=0.0, fee_bps=0.0)

    def reject_generator(bars, current_qty):
        return [OrderIntent(symbol="MSFT", side="buy", quantity=100.0)]

    risk_limits = RiskLimits(
        max_notional=10.0, max_position=1.0, max_consecutive_rejects=1
    )

    session_paths, handler = create_session("MSFT", "momentum")
    try:
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=reject_generator,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=clock,
            loop_config=LoopConfig(
                symbol="MSFT",
                strategy="momentum",
                interval="1m",
                window=_day_window(start),
                max_loops=10,
            ),
        )
        runner.run()
    finally:
        detach_handler(handler)

    with session_paths.state_events_file.open("r", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    assert any(
        event.get("reason") == "reject_limit_reached"
        for event in events
        if event.get("type") == "circuit_breaker"
    )
