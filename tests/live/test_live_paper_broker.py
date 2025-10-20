"""Lifecycle, inventory, and PnL tests for the deterministic paper broker."""

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
def broker(
    metadata_registry: SymbolMetadataRegistry, account_state: Account
) -> PaperBroker:
    return PaperBroker(
        metadata_registry=metadata_registry, starting_account=account_state
    )


def _intent(
    symbol: str,
    side: OrderSide,
    metadata_registry: SymbolMetadataRegistry,
    quantity: Decimal,
    limit_price: Decimal,
) -> OrderIntent:
    metadata = metadata_registry.resolve(symbol)
    return OrderIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=Pricing(limit=limit_price),
        notional=limit_price * quantity,
        metadata=metadata,
        sizing=SizingInstruction.fixed_notional(limit_price * quantity),
    )


def test_fifo_inventory_tracks_remaining_quantity(
    broker: PaperBroker,
    metadata_registry: SymbolMetadataRegistry,
) -> None:
    buy_intent = _intent(
        "BTC-USD", OrderSide.BUY, metadata_registry, Decimal("1"), Decimal("30000")
    )
    sell_intent = _intent(
        "BTC-USD", OrderSide.SELL, metadata_registry, Decimal("0.6"), Decimal("32000")
    )

    buy_order = broker.submit_order(buy_intent)
    broker.record_fill(buy_order.id, price=Decimal("30000"), quantity=Decimal("0.5"))
    assert buy_order.status is OrderStatus.PARTIALLY_FILLED
    broker.record_fill(buy_order.id, price=Decimal("30500"), quantity=Decimal("0.5"))
    assert buy_order.status is OrderStatus.FILLED

    sell_order = broker.submit_order(sell_intent)
    broker.record_fill(sell_order.id, price=Decimal("32000"), quantity=Decimal("0.6"))

    snapshot = broker.account_snapshot()
    position = snapshot.positions["BTC-USD"]
    assert position.quantity == Decimal("0.4")
    assert position.average_price == Decimal("30500")


def test_deterministic_fills_and_order_lifecycle_transitions(
    broker: PaperBroker,
) -> None:
    intent = _intent(
        "AAPL", OrderSide.BUY, broker.metadata_registry, Decimal("10"), Decimal("170")
    )
    order = broker.submit_order(intent)

    assert order.status is OrderStatus.NEW

    broker.record_fill(order.id, price=Decimal("170.00"), quantity=Decimal("4"))
    assert order.status is OrderStatus.PARTIALLY_FILLED

    broker.record_fill(order.id, price=Decimal("170.10"), quantity=Decimal("6"))
    assert order.status is OrderStatus.FILLED

    with pytest.raises(ValueError):
        broker.record_fill(order.id, price=Decimal("170.10"), quantity=Decimal("1"))


def test_event_logging_emits_all_transitions(broker: PaperBroker) -> None:
    intent = _intent(
        "AAPL", OrderSide.BUY, broker.metadata_registry, Decimal("5"), Decimal("171")
    )
    order = broker.submit_order(intent)
    broker.record_fill(order.id, price=Decimal("171.00"), quantity=Decimal("2"))
    broker.cancel_order(order.id)

    events = broker.events_for_order(order.id)
    assert [event.type for event in events] == [
        EventType.SUBMITTED,
        EventType.FILL,
        EventType.CANCELLED,
    ]
    for entry in events:
        assert "ts" in entry.payload
    assert order.status is OrderStatus.CANCELLED


def test_account_snapshot_updates_on_fills_and_cancels(broker: PaperBroker) -> None:
    intent = _intent(
        "BTC-USD",
        OrderSide.BUY,
        broker.metadata_registry,
        Decimal("0.3"),
        Decimal("30000"),
    )
    order = broker.submit_order(intent)

    broker.record_fill(order.id, price=Decimal("30000"), quantity=Decimal("0.2"))
    broker.cancel_order(order.id)

    snapshot = broker.account_snapshot()
    assert snapshot.positions["BTC-USD"].quantity == Decimal("0.2")
    assert any(
        event.type is EventType.CANCELLED for event in broker.events_for_order(order.id)
    )


def test_realized_and_unrealized_pnl_fifo(
    broker: PaperBroker,
    metadata_registry: SymbolMetadataRegistry,
) -> None:
    buy_intent = _intent(
        "BTC-USD", OrderSide.BUY, metadata_registry, Decimal("1"), Decimal("30000")
    )
    sell_intent = _intent(
        "BTC-USD", OrderSide.SELL, metadata_registry, Decimal("0.6"), Decimal("32000")
    )

    buy_order = broker.submit_order(buy_intent)
    broker.record_fill(buy_order.id, price=Decimal("30000"), quantity=Decimal("0.5"))
    broker.record_fill(buy_order.id, price=Decimal("30500"), quantity=Decimal("0.5"))

    sell_order = broker.submit_order(sell_intent)
    broker.record_fill(sell_order.id, price=Decimal("32000"), quantity=Decimal("0.6"))

    snapshot = broker.account_snapshot()
    assert snapshot.realized_pnl == Decimal("1150")
    assert snapshot.unrealized_pnl == Decimal("600")
    assert snapshot.positions["BTC-USD"].quantity == Decimal("0.4")
    assert snapshot.positions["BTC-USD"].average_price == Decimal("30500")


def test_fee_and_slippage_applied_deterministically(
    metadata_registry: SymbolMetadataRegistry,
    account_state: Account,
) -> None:
    broker = PaperBroker(
        metadata_registry=metadata_registry,
        starting_account=account_state,
        slippage_bps=Decimal("10"),
        maker_fee_bps=Decimal("1"),
        taker_fee_bps=Decimal("2"),
    )

    intent = _intent(
        "AAPL", OrderSide.BUY, metadata_registry, Decimal("1"), Decimal("100")
    )
    order = broker.submit_order(intent)
    broker.record_fill(
        order.id, price=Decimal("100"), quantity=Decimal("1"), liquidity="maker"
    )

    events = broker.events_for_order(order.id)
    assert len(events) == 2
    fill_payload = events[1].payload
    assert fill_payload["base_price"] == Decimal("100")
    assert fill_payload["price"] == Decimal("100.1")
    assert fill_payload["fee"] == Decimal("0.01001")
    assert fill_payload["liquidity"] == "maker"

    snapshot = broker.account_snapshot()
    assert snapshot.realized_pnl == Decimal("-0.01001")
    assert snapshot.unrealized_pnl == Decimal("0")
