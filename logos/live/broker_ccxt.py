"""Deterministic CCXT dry-run broker adapter."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from itertools import count
from typing import Dict, List, Optional

from .broker_base import (
    AccountSnapshot,
    BrokerAdapter,
    Fill,
    Order,
    OrderIntent,
    OrderState,
    Position,
    SymbolMeta,
)
from .time import TimeProvider, SystemTimeProvider


def _serialize(obj):  # type: ignore[no-untyped-def]
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(value) for value in obj]
    return obj


@dataclass
class CCXTBrokerAdapter(BrokerAdapter):
    """Dry-run CCXT adapter that validates intents and records actions."""

    exchange: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    time_provider: TimeProvider = field(default_factory=SystemTimeProvider)
    dry_run: bool = True

    def __post_init__(self) -> None:
        self._logs: List[dict] = []
        self._orders: Dict[str, Order] = {}
        self._seq = count(1)

    # ------------------------------------------------------------------
    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        meta = SymbolMeta(symbol=symbol)
        self._log("symbol_meta", symbol=symbol, meta=_serialize(meta))
        return meta

    def place_order(self, intent: OrderIntent) -> Order:
        if not self.dry_run:
            raise NotImplementedError("Live CCXT integration not implemented")
        self._validate_intent(intent)
        order_id = self._next_id()
        order = Order(order_id=order_id, intent=intent, state=OrderState.SUBMITTED)
        self._orders[order_id] = order
        self._log("order_submitted", order=_serialize(order))
        return order

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        self._validate_intent(intent)
        order = self._orders[order_id]
        order.intent = intent
        order.state = OrderState.SUBMITTED
        self._log("order_replaced", order=_serialize(order))
        return order

    def cancel_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        order = self._orders[order_id]
        order.state = OrderState.CANCELED
        self._log("order_cancelled", order=_serialize(order))
        return order

    def poll_fills(self) -> list[Fill]:
        self._log("poll_fills", fills=[])
        return []

    def get_positions(self) -> list[Position]:
        self._log("positions", positions=[])
        return []

    def get_account(self) -> AccountSnapshot:
        snapshot = AccountSnapshot(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            ts=self.time_provider.utc_now().timestamp(),
        )
        self._log("account_snapshot", account=_serialize(snapshot))
        return snapshot

    def reconcile(self) -> None:
        self._log("reconcile", info="noop")

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        self._log("market_data", symbol=symbol, price=price, ts=ts)

    # ------------------------------------------------------------------
    @property
    def logs(self) -> List[dict]:
        return list(self._logs)

    def reset_logs(self) -> None:
        self._logs.clear()

    # ------------------------------------------------------------------
    def _next_id(self) -> str:
        return f"CCXT-DRY-{next(self._seq):06d}"

    def _validate_intent(self, intent: OrderIntent) -> None:
        if intent.quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if intent.side not in {"buy", "sell"}:
            raise ValueError(f"Unsupported side '{intent.side}'")
        if intent.order_type not in {"market", "limit"}:
            raise ValueError(f"Unsupported order type '{intent.order_type}'")
        if intent.order_type == "limit" and intent.limit_price is None:
            raise ValueError("Limit orders require limit_price")

    def _log(self, event: str, **payload: object) -> None:
        entry = {
            "adapter": f"ccxt:{self.exchange}",
            "event": event,
            "ts": self.time_provider.utc_now().isoformat(),
            "payload": _serialize(payload),
        }
        self._logs.append(entry)

