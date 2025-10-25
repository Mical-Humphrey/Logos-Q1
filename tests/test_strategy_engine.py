import datetime as dt
from collections.abc import Iterator

import pandas as pd
import pytest

from logos.live.broker_base import SymbolMeta
from logos.live.broker_paper import PaperBrokerAdapter
from logos.live.order_sizing import SizingConfig
from logos.live.strategy_engine import StrategyOrderGenerator, StrategySpec
from logos.live.data_feed import Bar


@pytest.fixture()
def strategy_name(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    from logos import strategies as strategy_module

    def fake_strategy(frame: pd.DataFrame, **_: float) -> pd.Series:
        # Emit incremental integers so the latest signal increases with data.
        return pd.Series(range(len(frame)), index=frame.index)

    key = "unit_test_strategy"
    monkeypatch.setitem(strategy_module.STRATEGIES, key, fake_strategy)
    yield key
    monkeypatch.delitem(strategy_module.STRATEGIES, key, raising=False)


def _bar(ts: dt.datetime, price: float) -> Bar:
    return Bar(
        dt=ts,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1_000,
        symbol="MSFT",
    )


def test_generator_quantizes_to_symbol_meta(strategy_name: str) -> None:
    broker = PaperBrokerAdapter(slippage_bps=0.0, fee_bps=0.0)
    broker.set_symbol_meta(
        SymbolMeta(symbol="MSFT", quantity_precision=0, step_size=5, price_precision=2)
    )
    spec = StrategySpec(
        symbol="MSFT",
        strategy=strategy_name,
        params={},
        dollar_per_trade=1_234.0,
        sizing=SizingConfig(max_notional=5_000.0, max_position=100.0),
    )
    generator = StrategyOrderGenerator(broker, spec)
    start = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    bars = [_bar(start + dt.timedelta(minutes=i), price=101.0 + i) for i in range(3)]

    # Warmup bars should not trigger orders until enough history accumulates.
    assert generator.process([bars[0]], current_qty=0.0) == []

    intents = generator.process([bars[1]], current_qty=0.0)
    assert len(intents) == 1
    intent = intents[0]
    assert intent.side == "buy"
    # Quantity is quantized to the step size of 5 shares.
    assert intent.quantity == pytest.approx(10.0)

    # Once in position the generator targets a higher signal-scaled quantity.
    followup = generator.process([bars[2]], current_qty=intent.quantity)
    assert len(followup) == 1
    assert followup[0].quantity == pytest.approx(15.0)
    assert followup[0].side == "buy"


def test_generator_clamps_notional(strategy_name: str) -> None:
    broker = PaperBrokerAdapter(slippage_bps=0.0, fee_bps=0.0)
    broker.set_symbol_meta(
        SymbolMeta(symbol="MSFT", quantity_precision=0, step_size=1, price_precision=2)
    )
    spec = StrategySpec(
        symbol="MSFT",
        strategy=strategy_name,
        params={},
        dollar_per_trade=10_000.0,
        sizing=SizingConfig(max_notional=5_000.0, max_position=1_000.0),
    )
    generator = StrategyOrderGenerator(broker, spec)
    bars = [
        _bar(dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc), price=100.0),
        _bar(dt.datetime(2025, 1, 1, 9, 31, tzinfo=dt.timezone.utc), price=100.0),
    ]

    assert generator.process([bars[0]], current_qty=0.0) == []
    intents = generator.process([bars[1]], current_qty=0.0)
    assert len(intents) == 1
    intent = intents[0]
    # Clamp scales to the max_notional (5_000) -> 50 shares at $100.
    assert intent.quantity == pytest.approx(50.0)
    assert intent.side == "buy"


def test_generator_preserves_sorted_timestamp_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from logos import strategies as strategy_module

    captured_indices: list[pd.DatetimeIndex] = []

    def capturing_strategy(frame: pd.DataFrame, **_: float) -> pd.Series:
        captured_indices.append(pd.DatetimeIndex(frame.index.copy()))
        return pd.Series(range(len(frame)), index=frame.index)

    key = "timestamp_capture_strategy"
    monkeypatch.setitem(strategy_module.STRATEGIES, key, capturing_strategy)

    broker = PaperBrokerAdapter(slippage_bps=0.0, fee_bps=0.0)
    broker.set_symbol_meta(
        SymbolMeta(symbol="MSFT", quantity_precision=0, step_size=1, price_precision=2)
    )
    spec = StrategySpec(
        symbol="MSFT",
        strategy=key,
        params={},
        dollar_per_trade=1_000.0,
        sizing=SizingConfig(max_notional=0.0, max_position=1_000.0),
    )
    generator = StrategyOrderGenerator(broker, spec)

    base = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc)
    newer = base + dt.timedelta(minutes=1)

    generator.process([_bar(newer, 101.0), _bar(base, 100.0)], current_qty=0.0)

    assert captured_indices, "strategy should have been invoked"
    idx = captured_indices[-1]
    assert isinstance(idx, pd.DatetimeIndex)
    assert idx.is_monotonic_increasing
    assert idx.tz is not None
    assert idx[-1] == newer

    monkeypatch.delitem(strategy_module.STRATEGIES, key, raising=False)
