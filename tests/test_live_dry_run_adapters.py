from __future__ import annotations

import dataclasses
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