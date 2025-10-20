"""Core broker abstractions shared by live adapters.

The real adapters (paper, CCXT, Alpaca, IB) all inherit from
:class:`BrokerAdapter`.  The goal is to keep order lifecycle handling,
precision rules, and account snapshots consistent across integrations.

TODO:
- Capture exchange-specific order types (stop, trailing) once needed.
- Extend SymbolMeta with maker/taker fee schedules or tiering data.
- Introduce persistence hooks for audit-grade order journaling.
"""

from __future__ import annotations

import abc
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


class OrderState(str, Enum):
    """Lifecycle states for an order."""

    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class SymbolMeta:
    """Precision and sizing rules for a traded symbol."""

    symbol: str
    price_precision: int = 2
    quantity_precision: int = 6
    min_notional: float = 0.0
    min_qty: float = 0.0
    step_size: float = 0.0


@dataclass
class OrderIntent:
    """Desired change in position submitted to a broker."""

    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"
    limit_price: Optional[float] = None
    time_in_force: str = "gtc"
    client_order_id: Optional[str] = None


@dataclass
class Order:
    """Broker-acknowledged order."""

    order_id: str
    intent: OrderIntent
    state: OrderState
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    broker_order_id: Optional[str] = None
    reject_reason: Optional[str] = None


@dataclass
class Fill:
    """Execution record linking fills back to orders."""

    order_id: str
    fill_id: str
    price: float
    quantity: float
    fees: float
    slip_bps: float
    ts: float


@dataclass
class Position:
    """Current holdings for a symbol."""

    symbol: str
    quantity: float
    avg_price: float
    unrealized_pnl: float = 0.0


@dataclass
class AccountSnapshot:
    """Aggregated account information from the broker."""

    equity: float
    cash: float
    buying_power: float
    ts: float
    currency: str = "USD"


def quantize_order(qty: float, price: float, meta: SymbolMeta) -> Tuple[float, float]:
    """Clamp quantity and price to broker-supported increments."""

    q = qty
    p = price
    if meta.step_size:
        steps = round(q / meta.step_size)
        q = steps * meta.step_size
    if meta.quantity_precision >= 0:
        q = round(q, meta.quantity_precision)
    if meta.price_precision >= 0:
        p = round(p, meta.price_precision)
    return q, p


def meets_minimums(qty: float, price: float, meta: SymbolMeta) -> bool:
    notional = abs(qty * price)
    if meta.min_qty and abs(qty) < meta.min_qty:
        return False
    if meta.min_notional and notional < meta.min_notional:
        return False
    return True


class BrokerAdapter(abc.ABC):
    """Common contract implemented by all broker adapters."""

    @abc.abstractmethod
    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        """Return sizing/precision information for ``symbol``."""

    @abc.abstractmethod
    def place_order(self, intent: OrderIntent) -> Order:
        """Submit an order to the broker."""

    @abc.abstractmethod
    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        """Replace an existing order with new parameters."""

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an existing order."""

    @abc.abstractmethod
    def poll_fills(self) -> List[Fill]:
        """Return new fills since the previous call."""

    @abc.abstractmethod
    def get_positions(self) -> List[Position]:
        """Return current positions."""

    @abc.abstractmethod
    def get_account(self) -> AccountSnapshot:
        """Return an account snapshot."""

    @abc.abstractmethod
    def reconcile(self) -> None:
        """Force a reconciliation against the remote broker state."""

    @abc.abstractmethod
    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        """Update internal marks from latest traded price."""


@dataclass
class OrderJournal:
    """Minimal in-memory history of order transitions."""

    events: Dict[str, List[Order]] = field(default_factory=dict)

    def record(self, order: Order) -> None:
        self.events.setdefault(order.order_id, []).append(dataclasses.replace(order))

    def history(self, order_id: str) -> Iterable[Order]:
        return tuple(self.events.get(order_id, ()))
