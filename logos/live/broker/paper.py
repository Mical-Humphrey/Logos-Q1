"""Deterministic paper broker with FIFO inventory, PnL, and event logging."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from typing import Dict, Iterator, List, Optional

from logos.live.types import (
    Account,
    Event,
    EventType,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    Position,
)


BPS = Decimal("0.0001")


@dataclass
class _InventoryLot:
    """Internal FIFO lot used for deterministic inventory tracking."""

    quantity: Decimal
    price: Decimal


class PaperBroker:
    """Deterministic paper broker with FIFO inventory and lifecycle events."""

    def __init__(
        self,
        metadata_registry,
        starting_account: Account,
        clock: Optional[Iterator[int]] = None,
        slippage_bps: Decimal | float = Decimal("0"),
        maker_fee_bps: Decimal | float = Decimal("0"),
        taker_fee_bps: Decimal | float = Decimal("0"),
    ) -> None:
        self.metadata_registry = metadata_registry
        self._clock = clock or count()
        self._order_sequence = count(1)
        self._orders: Dict[str, Order] = {}
        self._events: Dict[str, List[Event]] = {}
        self._inventory: Dict[str, List[_InventoryLot]] = {}
        self._cash = starting_account.cash
        self._realized_pnl = Decimal("0")
        self._last_price: Dict[str, Decimal] = {}
        self._slippage_bps = Decimal(str(slippage_bps))
        self._maker_fee_bps = Decimal(str(maker_fee_bps))
        self._taker_fee_bps = Decimal(str(taker_fee_bps))
        self._initialise_inventory(starting_account)

    def submit_order(self, intent: OrderIntent) -> Order:
        if intent.quantity <= Decimal("0"):
            raise ValueError("Deterministic fills require a non-zero order quantity")

        order_id = self._next_order_id()
        order = Order(
            id=order_id,
            intent=intent,
            status=OrderStatus.NEW,
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )
        self._orders[order_id] = order
        self._log_event(
            order_id,
            EventType.SUBMITTED,
            base_price=None,
            executed_price=None,
            quantity=None,
            fee=None,
            liquidity=None,
        )
        return order

    def record_fill(
        self,
        order_id: str,
        *,
        price: Decimal,
        quantity: Decimal,
        liquidity: str = "taker",
    ) -> None:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Unknown order id '{order_id}'")
        if order.status is OrderStatus.CANCELLED:
            raise ValueError("Cannot fill a cancelled order")
        if order.status is OrderStatus.FILLED:
            raise ValueError("Order already filled")
        if quantity <= Decimal("0"):
            raise ValueError("Fill quantity must be greater than zero")
        if liquidity not in {"maker", "taker"}:
            raise ValueError("Liquidity must be 'maker' or 'taker'")

        new_filled = order.filled_quantity + quantity
        if new_filled > order.intent.quantity:
            raise ValueError("Fill quantity exceeds order quantity")

        base_price = price
        executed_price = self._apply_slippage(order.intent.side, base_price)
        notional = executed_price * quantity
        fee = self._calculate_fee(notional, liquidity)

        prev_notional = (order.avg_fill_price or Decimal("0")) * order.filled_quantity
        fill_notional = executed_price * quantity
        order.filled_quantity = new_filled
        order.avg_fill_price = (prev_notional + fill_notional) / new_filled

        if order.intent.side is OrderSide.BUY:
            self._record_buy_fill(order.intent.symbol, quantity, executed_price, fee)
        else:
            self._record_sell_fill(order.intent.symbol, quantity, executed_price, fee)

        self._last_price[order.intent.symbol] = executed_price
        order.status = (
            OrderStatus.FILLED
            if order.filled_quantity == order.intent.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        self._log_event(
            order_id,
            EventType.FILL,
            base_price=base_price,
            executed_price=executed_price,
            quantity=quantity,
            fee=fee,
            liquidity=liquidity,
        )

    def cancel_order(self, order_id: str) -> None:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Unknown order id '{order_id}'")
        if order.status is OrderStatus.FILLED:
            return
        if order.status is OrderStatus.CANCELLED:
            return

        order.status = OrderStatus.CANCELLED
        self._log_event(
            order_id,
            EventType.CANCELLED,
            base_price=None,
            executed_price=None,
            quantity=None,
            fee=None,
            liquidity=None,
        )

    def account_snapshot(self) -> Account:
        positions: Dict[str, Position] = {}
        inventory_value = Decimal("0")
        unrealized = Decimal("0")
        for symbol, lots in self._inventory.items():
            total_quantity = sum((lot.quantity for lot in lots), start=Decimal("0"))
            if total_quantity == 0:
                continue
            weighted_notional = sum(
                (lot.quantity * lot.price for lot in lots), start=Decimal("0")
            )
            average_price = weighted_notional / total_quantity
            mark_price = self._last_price.get(symbol, average_price)
            positions[symbol] = Position(
                symbol=symbol,
                quantity=total_quantity,
                average_price=average_price,
            )
            inventory_value += mark_price * total_quantity
            unrealized += (mark_price - average_price) * total_quantity

        equity = self._cash + inventory_value
        return Account(
            equity=equity,
            cash=self._cash,
            positions=positions,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized,
        )

    def events_for_order(self, order_id: str) -> List[Event]:
        return list(self._events.get(order_id, []))

    def _initialise_inventory(self, starting_account: Account) -> None:
        for symbol, position in starting_account.positions.items():
            if position.quantity == 0:
                continue
            self._inventory.setdefault(symbol, []).append(
                _InventoryLot(quantity=position.quantity, price=position.average_price)
            )
            self._last_price[symbol] = position.average_price

    def _record_buy_fill(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> None:
        lots = self._inventory.setdefault(symbol, [])
        lots.append(_InventoryLot(quantity=quantity, price=price))
        notional = price * quantity
        self._cash -= notional + fee
        self._realized_pnl -= fee

    def _record_sell_fill(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> None:
        lots = self._inventory.get(symbol, [])
        remaining = quantity
        idx = 0
        realized = Decimal("0")
        while remaining > 0 and idx < len(lots):
            lot = lots[idx]
            consume = min(lot.quantity, remaining)
            lot.quantity -= consume
            remaining -= consume
            realized += (price - lot.price) * consume
            if lot.quantity == 0:
                idx += 1
        if remaining > 0:
            raise ValueError(f"Insufficient inventory to sell {quantity} {symbol}")
        if idx:
            del lots[:idx]
        notional = price * quantity
        self._cash += notional - fee
        self._realized_pnl += realized - fee

    def _next_order_id(self) -> str:
        return f"PB-{next(self._order_sequence):06d}"

    def _log_event(
        self,
        order_id: str,
        event_type: EventType,
        *,
        base_price: Optional[Decimal],
        executed_price: Optional[Decimal],
        quantity: Optional[Decimal],
        fee: Optional[Decimal],
        liquidity: Optional[str],
    ) -> None:
        order = self._orders[order_id]
        payload: Dict[str, object] = {
            "ts": Decimal(next(self._clock)),
            "base_price": base_price,
            "price": executed_price,
            "quantity": quantity,
            "status": order.status.value,
            "fee": fee,
            "liquidity": liquidity,
        }
        self._events.setdefault(order_id, []).append(
            Event(order_id=order_id, type=event_type, payload=payload)
        )

    def _apply_slippage(self, side: OrderSide, price: Decimal) -> Decimal:
        if self._slippage_bps == 0:
            return price
        adjustment = price * self._slippage_bps * BPS
        return price + adjustment if side is OrderSide.BUY else price - adjustment

    def _calculate_fee(self, notional: Decimal, liquidity: str) -> Decimal:
        if notional == 0:
            return Decimal("0")
        bps = self._taker_fee_bps if liquidity == "taker" else self._maker_fee_bps
        return notional * bps * BPS
