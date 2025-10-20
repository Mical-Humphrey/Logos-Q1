from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from logos.live.broker_alpaca import AlpacaBrokerAdapter
from logos.live.broker_ccxt import CCXTBrokerAdapter
from logos.live.broker_base import OrderIntent, OrderState
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
    req = log_entry["request"]
    resp = log_entry["response"]

    assert log_entry["adapter"] == "alpaca"
    assert log_entry["adapter_mode"] == "dry-run"
    assert log_entry["client_order_id"] == resp["client_order_id"]
    assert req["run_id"] == "run-001"
    assert req["seed"] == 42
    assert req["venue"] == "alpaca"
    assert req["symbol"] == "AAPL"
    assert req["order_type"] == "limit"
    assert req["time_in_force"] == "gtc"
    assert req["qty"] == "10"
    assert req["price"] == "150.5"
    assert len(req["intent_hash"]) == 64
    assert len(resp["validation_hash"]) == 64
    assert resp["normalized_payload"] == req
    assert resp["adapter_mode"] == "dry-run"
    assert resp["accepted"] is True
    assert len(resp["client_order_id"]) <= 48

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


def test_alpaca_rejects_invalid_time_in_force() -> None:
    clock = _clock()
    adapter = AlpacaBrokerAdapter(
        base_url="alpaca-paper",
        key_id="KEY",
        secret_key="SECRET",
        run_id="run-002",
        seed=101,
        time_provider=clock,
    )
    bad_intent = dataclasses.replace(_limit_intent(), time_in_force="gtd")

    with pytest.raises(ValueError) as exc:
        adapter.place_order(bad_intent)
    assert "invalid_time_in_force" in str(exc.value)

    log_entry = adapter.logs[-1]
    resp = log_entry["response"]
    assert resp["accepted"] is False
    assert resp["reason"] == "invalid_time_in_force"
    assert resp["normalized_payload"]["time_in_force"] == "gtd"


def test_alpaca_replace_and_cancel_flow() -> None:
    clock = _clock()
    adapter = AlpacaBrokerAdapter(
        base_url="alpaca-paper",
        key_id="KEY",
        secret_key="SECRET",
        run_id="run-003",
        seed=303,
        time_provider=clock,
    )
    intent = _limit_intent()
    order = adapter.place_order(intent)
    amended_intent = dataclasses.replace(intent, limit_price=151.25)
    clock.advance(dt.timedelta(minutes=1))
    updated = adapter.replace_order(order.order_id, amended_intent)
    assert updated.intent.limit_price == 151.25

    clock.advance(dt.timedelta(minutes=1))
    canceled = adapter.cancel_order(order.order_id)
    assert canceled.state is OrderState.CANCELED

    actions = [entry["action"] for entry in adapter.drain_logs()]
    assert actions == ["place_order", "replace_order", "cancel_order"]


def test_alpaca_account_and_market_helpers() -> None:
    clock = _clock()
    adapter = AlpacaBrokerAdapter(
        base_url="alpaca-paper",
        key_id="KEY",
        secret_key="SECRET",
        run_id="run-004",
        seed=404,
        time_provider=clock,
    )
    meta = adapter.get_symbol_meta("AAPL")
    assert meta.symbol == "AAPL"

    snapshot = adapter.get_account()
    assert snapshot.cash == 0.0
    assert adapter.get_positions() == []
    assert adapter.poll_fills() == []

    adapter.reconcile()
    adapter.on_market_data("AAPL", 150.0, clock.utc_now().timestamp())


def test_ccxt_replace_order_updates_state() -> None:
    clock = _clock()
    adapter = CCXTBrokerAdapter(
        exchange="ftx",
        run_id="run-ccc",
        seed=12,
        time_provider=clock,
    )
    intent = _limit_intent(symbol="BTC/USD")
    order = adapter.place_order(intent)
    new_intent = dataclasses.replace(intent, limit_price=26_000.5)
    clock.advance(dt.timedelta(minutes=1))
    updated = adapter.replace_order(order.order_id, new_intent)
    assert updated.intent.limit_price == 26_000.5

    clock.advance(dt.timedelta(minutes=1))
    canceled = adapter.cancel_order(order.order_id)
    assert canceled.state is OrderState.CANCELED

    actions = [entry["action"] for entry in adapter.drain_logs()]
    assert actions == ["place_order", "replace_order", "cancel_order"]


def test_ccxt_account_helpers_are_stubbed() -> None:
    clock = _clock()
    adapter = CCXTBrokerAdapter(
        exchange="coinbase",
        run_id="run-acc",
        seed=55,
        time_provider=clock,
    )
    snapshot = adapter.get_account()
    assert snapshot.equity == 0.0
    assert adapter.get_positions() == []
    assert adapter.poll_fills() == []
    adapter.reconcile()
    adapter.on_market_data("BTC/USD", 25_000.0, clock.utc_now().timestamp())


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
    req = log_entry["request"]
    resp = log_entry["response"]
    assert log_entry["adapter"] == "ccxt"
    assert log_entry["adapter_mode"] == "dry-run"
    assert log_entry["order_id"] is None
    assert req["venue"] == "binance"
    assert resp["accepted"] is False
    assert resp["reason"] == "qty_not_positive"
    assert len(resp["client_order_id"]) <= 48
    assert resp["normalized_payload"] == req


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
    assert cancel_log["adapter_mode"] == "dry-run"
    assert cancel_log["response"]["accepted"] is True
    assert cancel_log["response"]["normalized_payload"]["client_order_id"] == place_log["response"]["client_order_id"]