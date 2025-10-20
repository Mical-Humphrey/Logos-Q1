"""Failing-first tests for the deterministic paper broker.

The broker is expected to provide FIFO inventory, deterministic fills, rich
lifecycle events, and account snapshots. These tests currently fail because the
paper broker has only been scaffolded.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from logos.live.broker.paper import PaperBroker
from logos.live.translator import SymbolMetadataRegistry
from logos.live.types import (
    Account,
    EventType,
    OrderIntent,
    OrderSide,
    OrderStatus,
    Pricing,
    SizingInstruction,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live"


@pytest.fixture(scope="module")
def metadata_registry() -> SymbolMetadataRegistry:
    return SymbolMetadataRegistry.from_yaml(FIXTURES / "symbols.yaml")


@pytest.fixture(scope="module")
def account_state() -> Account:
    payload = json.loads((FIXTURES / "account_start.json").read_text())
    return Account(
        equity=Decimal(str(payload["equity"])),
        cash=Decimal(str(payload["cash"])),
        positions={},
    )


@pytest.fixture()
def broker(metadata_registry: SymbolMetadataRegistry, account_state: Account) -> PaperBroker:
    return PaperBroker(metadata_registry=metadata_registry, starting_account=account_state)


def _intent(symbol: str, side: OrderSide, metadata_registry: SymbolMetadataRegistry) -> OrderIntent:
    metadata = metadata_registry.resolve(symbol)
    return OrderIntent(
        symbol=symbol,
        side=side,
        quantity=Decimal("0"),
        price=Pricing(limit=Decimal("0")),
        notional=Decimal("0"),
        metadata=metadata,
        sizing=SizingInstruction.fixed_notional(Decimal("0")),
    )


def test_fifo_inventory_and_realized_unrealized_pnl(
    broker: PaperBroker,
    metadata_registry: SymbolMetadataRegistry,
) -> None:
    buy_intent = _intent("BTC-USD", OrderSide.BUY, metadata_registry)
    sell_intent = _intent("BTC-USD", OrderSide.SELL, metadata_registry)

    buy_order = broker.submit_order(buy_intent)
    broker.record_fill(buy_order.id, price=Decimal("30000"), quantity=Decimal("0.5"))
    broker.record_fill(buy_order.id, price=Decimal("30500"), quantity=Decimal("0.5"))

    sell_order = broker.submit_order(sell_intent)
    broker.record_fill(sell_order.id, price=Decimal("32000"), quantity=Decimal("0.6"))

    snapshot = broker.account_snapshot()
    assert snapshot.realized_pnl == Decimal("900")
    assert snapshot.unrealized_pnl == Decimal("200")
    assert snapshot.positions["BTC-USD"].quantity == Decimal("0.4")


def test_deterministic_fills_and_order_lifecycle_transitions(broker: PaperBroker) -> None:
    intent = _intent("AAPL", OrderSide.BUY, broker.metadata_registry)
    order = broker.submit_order(intent)

    assert order.status is OrderStatus.NEW

    broker.record_fill(order.id, price=Decimal("170.00"), quantity=Decimal("10"))
    assert order.status is OrderStatus.FILLED

    with pytest.raises(ValueError):
        broker.record_fill(order.id, price=Decimal("170.00"), quantity=Decimal("1"))


def test_event_logging_emits_all_transitions(broker: PaperBroker) -> None:
    intent = _intent("AAPL", OrderSide.SELL, broker.metadata_registry)
    order = broker.submit_order(intent)
    broker.record_fill(order.id, price=Decimal("171.00"), quantity=Decimal("5"))
    broker.cancel_order(order.id)

    event_types = [event.type for event in broker.events_for_order(order.id)]
    assert event_types == [
        EventType.SUBMITTED,
        EventType.FILL,
        EventType.CANCELLED,
    ]


def test_account_snapshot_updates_on_fills_and_cancels(broker: PaperBroker) -> None:
    intent = _intent("BTC-USD", OrderSide.BUY, broker.metadata_registry)
    order = broker.submit_order(intent)

    broker.record_fill(order.id, price=Decimal("30000"), quantity=Decimal("0.2"))
    broker.cancel_order(order.id)

    snapshot = broker.account_snapshot()
    assert snapshot.cash == Decimal("94000")
    assert snapshot.positions["BTC-USD"].quantity == Decimal("0.2")
    assert any(event.type is EventType.CANCELLED for event in broker.events_for_order(order.id))
