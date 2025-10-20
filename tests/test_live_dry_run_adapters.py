from __future__ import annotations

import datetime as dt

import pytest

from logos.live.broker_alpaca import AlpacaBrokerAdapter
from logos.live.broker_ccxt import CCXTBrokerAdapter
from logos.live.broker_base import OrderIntent
from logos.live.time import MockTimeProvider


def _clock() -> MockTimeProvider:
    return MockTimeProvider(current=dt.datetime(2024, 1, 1, 15, 30, tzinfo=dt.timezone.utc))


def _limit_intent(symbol: str = "AAPL") -> OrderIntent:
    return OrderIntent(symbol=symbol, side="buy", quantity=10.0, order_type="limit", limit_price=150.5)


def test_alpaca_dry_run_logs_are_deterministic() -> None:
    clock = _clock()
    adapter = AlpacaBrokerAdapter(
        base_url="alpaca-paper",
        key_id="KEY",
        secret_key="SECRET",
        run_id="run-001",
        seed=42,
        time_provider=clock,
    )
    order = adapter.place_order(_limit_intent())
    assert order.order_id == "ALPACA-DRY-000001"

    log_entry = adapter.logs[-1]
    assert log_entry["adapter"] == "alpaca"
    assert log_entry["venue"] == "alpaca-paper"
    assert log_entry["run_id"] == "run-001"
    assert log_entry["seed"] == 42
    assert log_entry["symbol"] == "AAPL"
    assert log_entry["qty"] == "10"
    assert log_entry["price"] == "150.5"
    assert log_entry["response"] == {"status": "accepted", "reason": None}
    assert isinstance(log_entry["intent_hash"], str) and len(log_entry["intent_hash"]) == 16

    # Deterministic: re-running with identical inputs yields identical log payload.
    clock_clone = _clock()
    adapter_clone = AlpacaBrokerAdapter(
        base_url="alpaca-paper",
        key_id="KEY",
        secret_key="SECRET",
        run_id="run-001",
        seed=42,
        time_provider=clock_clone,
    )
    adapter_clone.place_order(_limit_intent())
    assert adapter_clone.logs[-1] == log_entry


def test_ccxt_dry_run_rejects_and_logs_reason() -> None:
    clock = _clock()
    adapter = CCXTBrokerAdapter(
        exchange="binance",
        run_id="run-xyz",
        seed=7,
        time_provider=clock,
    )
    bad_intent = OrderIntent(symbol="BTC/USD", side="buy", quantity=0.0, order_type="limit", limit_price=25_000.0)

    with pytest.raises(ValueError):
        adapter.place_order(bad_intent)

    log_entry = adapter.logs[-1]
    assert log_entry["adapter"] == "ccxt"
    assert log_entry["venue"] == "binance"
    assert log_entry["order_id"] == "CCXT-DRY-000001"
    assert log_entry["response"] == {"status": "rejected", "reason": "non_positive_quantity"}
    assert log_entry["intent_hash"] is not None


def test_ccxt_cancel_uses_existing_order_payload() -> None:
    clock = _clock()
    adapter = CCXTBrokerAdapter(
        exchange="kraken",
        run_id="run-abc",
        seed=9,
        time_provider=clock,
    )
    intent = _limit_intent(symbol="BTC/USD")
    order = adapter.place_order(intent)
    adapter.cancel_order(order.order_id)

    place_log, cancel_log = adapter.logs[-2:]
    assert place_log["order_id"] == order.order_id
    assert cancel_log["order_id"] == order.order_id
    assert cancel_log["symbol"] == "BTC/USD"
    assert cancel_log["response"] == {"status": "accepted", "reason": None}