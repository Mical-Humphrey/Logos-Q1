"""Deterministic paper broker implementation used for testing."""

from __future__ import annotations

import itertools
import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .broker_base import (
    AccountSnapshot,
    BrokerAdapter,
    Fill,
    Order,
    OrderIntent,
    OrderJournal,
    OrderState,
    Position,
    SymbolMeta,
    meets_minimums,
    quantize_order,
)
from .time import TimeProvider, SystemTimeProvider


@dataclass
class PaperBrokerAdapter(BrokerAdapter):
    """Simple fill simulator that tracks cash and positions."""

    time_provider: TimeProvider = field(default_factory=SystemTimeProvider)
    starting_cash: float = 1_000_000.0
    slippage_bps: float = 1.0
    fee_bps: float = 0.0

    def __post_init__(self) -> None:
        self._cash = self.starting_cash
        self._orders: Dict[str, Order] = {}
        self._open_orders: Dict[str, Order] = {}
        self._order_seq = itertools.count(1)
        self._fill_seq = itertools.count(1)
        self._fills: List[Fill] = []
        self._journal = OrderJournal()
        self._positions: Dict[str, Dict[str, float]] = {}
        self._marks: Dict[str, float] = {}
        self._symbol_meta: Dict[str, SymbolMeta] = {}

    # ------------------------------------------------------------------
    # BrokerAdapter API
    # ------------------------------------------------------------------
    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        return self._symbol_meta.setdefault(symbol, SymbolMeta(symbol=symbol))

    def set_symbol_meta(self, meta: SymbolMeta) -> None:
        self._symbol_meta[meta.symbol] = meta

    def place_order(self, intent: OrderIntent) -> Order:
        meta = self.get_symbol_meta(intent.symbol)
        fallback_price = intent.limit_price if intent.limit_price is not None else price_or_default()
        mark = self._marks.get(intent.symbol, fallback_price)
        price_basis = intent.limit_price if intent.limit_price is not None else mark
        qty, price_basis = quantize_order(intent.quantity, price_basis, meta)
        if not meets_minimums(qty, price_basis, meta):
            return self._build_order(intent, OrderState.REJECTED, reject="min_requirements")
        if intent.order_type == "market":
            price_basis = mark
        intent = dataclasses.replace(intent, quantity=qty, limit_price=intent.limit_price)
        order = self._build_order(intent, OrderState.SUBMITTED)
        self._open_orders[order.order_id] = order
        return order

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        self.cancel_order(order_id)
        return self.place_order(intent)

    def cancel_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(order_id)
        if order.state in {OrderState.FILLED, OrderState.CANCELED}:
            return order
        updated = dataclasses.replace(order, state=OrderState.CANCELED)
        self._orders[order_id] = updated
        self._journal.record(updated)
        self._open_orders.pop(order_id, None)
        return updated

    def poll_fills(self) -> List[Fill]:
        fills, self._fills = self._fills, []
        return fills

    def get_positions(self) -> List[Position]:
        out: List[Position] = []
        for symbol, data in self._positions.items():
            mark = self._marks.get(symbol, data.get("avg_price", 0.0))
            unrealized = (mark - data["avg_price"]) * data["qty"]
            out.append(Position(symbol=symbol, quantity=data["qty"], avg_price=data["avg_price"], unrealized_pnl=unrealized))
        return out

    def get_account(self) -> AccountSnapshot:
        equity = self._cash
        for symbol, data in self._positions.items():
            mark = self._marks.get(symbol, data["avg_price"])
            equity += data["qty"] * mark
        return AccountSnapshot(equity=equity, cash=self._cash, buying_power=self._cash, ts=self.time_provider.utc_now().timestamp())

    def reconcile(self) -> None:
        # TODO: integrate with persistence/logs if needed.
        return

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        self._marks[symbol] = price
        for order in list(self._open_orders.values()):
            if order.intent.symbol != symbol:
                continue
            if self._try_fill(order, price, ts):
                self._open_orders.pop(order.order_id, None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_order(self, intent: OrderIntent, state: OrderState, reject: Optional[str] = None) -> Order:
        order_id = intent.client_order_id or f"PB-{next(self._order_seq):06d}"
        order = Order(order_id=order_id, intent=intent, state=state, reject_reason=reject)
        self._orders[order_id] = order
        self._journal.record(order)
        return order

    def _try_fill(self, order: Order, price: float, ts: float) -> bool:
        intent = order.intent
        side = intent.side
        meta = self.get_symbol_meta(intent.symbol)

        limit_price = intent.limit_price
        tradable = True
        if intent.order_type == "limit" and limit_price is not None:
            if side == "buy" and price > limit_price:
                tradable = False
            if side == "sell" and price < limit_price:
                tradable = False
        if not tradable:
            return False

        qty = intent.quantity
        signed_qty = qty if side == "buy" else -qty
        slip = price * (self.slippage_bps / 10_000)
        fill_price = price + slip if side == "buy" else price - slip
        if limit_price is not None:
            if side == "buy":
                fill_price = min(fill_price, limit_price)
            else:
                fill_price = max(fill_price, limit_price)
        fill_price = round(fill_price, meta.price_precision)
        fees = abs(fill_price * qty) * (self.fee_bps / 10_000)

        self._apply_fill(intent.symbol, signed_qty, fill_price, fees)

        updated = dataclasses.replace(order, state=OrderState.FILLED, filled_qty=qty, avg_fill_price=fill_price)
        self._orders[order.order_id] = updated
        self._journal.record(updated)
        fill = Fill(
            order_id=order.order_id,
            fill_id=f"PB-FILL-{next(self._fill_seq):06d}",
            price=fill_price,
            quantity=qty,
            fees=fees,
            slip_bps=self.slippage_bps,
            ts=ts,
        )
        self._fills.append(fill)
        return True

    def _apply_fill(self, symbol: str, signed_qty: float, price: float, fees: float) -> None:
        self._cash -= price * signed_qty
        self._cash -= fees
        pos = self._positions.setdefault(symbol, {"qty": 0.0, "avg_price": 0.0, "realized": 0.0})
        prev_qty = pos.get("qty", 0.0)
        avg_price = pos.get("avg_price", 0.0)
        new_qty = prev_qty + signed_qty

        realized = 0.0
        if prev_qty == 0 or prev_qty * signed_qty >= 0:
            if abs(new_qty) > 1e-9:
                pos["avg_price"] = ((prev_qty * avg_price) + (signed_qty * price)) / new_qty
            else:
                pos["avg_price"] = 0.0
        else:
            closed = min(abs(prev_qty), abs(signed_qty))
            if closed > 0:
                if prev_qty > 0:
                    realized += (price - avg_price) * closed
                else:
                    realized += (avg_price - price) * closed
            if abs(new_qty) > 1e-9 and abs(signed_qty) > abs(prev_qty):
                pos["avg_price"] = price
            else:
                pos["avg_price"] = 0.0 if abs(new_qty) <= 1e-9 else pos["avg_price"]
        pos["qty"] = new_qty
        pos["realized"] = pos.get("realized", 0.0) + realized

    # ------------------------------------------------------------------
    # Bootstrap helpers
    # ------------------------------------------------------------------
    def bootstrap_positions(self, positions: Dict[str, Dict[str, float]]) -> None:
        """Prime the simulator with pre-existing positions (for restarts)."""

        self._positions = {}
        for symbol, data in positions.items():
            qty = float(data.get("qty", 0.0))
            avg_price = float(data.get("avg_price", 0.0))
            if abs(qty) < 1e-9:
                continue
            realized = float(data.get("realized", 0.0))
            self._positions[symbol] = {"qty": qty, "avg_price": avg_price, "realized": realized}
            self._marks[symbol] = avg_price
        cash_offset = sum(pos["qty"] * pos["avg_price"] for pos in self._positions.values())
        self._cash = self.starting_cash - cash_offset


def price_or_default() -> float:
    return 1.0
