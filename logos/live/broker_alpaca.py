"""Deterministic Alpaca dry-run broker adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from .dry_run_validation import ValidationResult, validate_request
from .time import SystemTimeProvider, TimeProvider


ADAPTER_NAME = "alpaca"
VENUE_NAME = "alpaca"
ADAPTER_MODE = "dry-run"


@dataclass
class AlpacaBrokerAdapter(BrokerAdapter):
    """Dry-run Alpaca adapter with shared validation + deterministic logging."""

    base_url: str
    key_id: str
    secret_key: str
    run_id: str = "run-unknown"
    seed: int = 0
    time_provider: TimeProvider = field(default_factory=SystemTimeProvider)
    dry_run: bool = True

    def __post_init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._logs: List[dict] = []
        self._seq = count(1)

    @property
    def logs(self) -> List[dict]:
        return list(self._logs)

    def drain_logs(self) -> List[dict]:
        entries = list(self._logs)
        self._logs.clear()
        return entries

    def reset_logs(self) -> None:
        self._logs.clear()

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(symbol=symbol)

    def place_order(self, intent: OrderIntent) -> Order:
        if not self.dry_run:
            raise NotImplementedError("Live Alpaca integration not implemented")
        timestamp = self.time_provider.utc_now().isoformat()
        # NOTE: validate_request applies the shared dry-run policy, including the
        # deterministic client_order_id derived from seed + intent hash.
        validation = validate_request(
            adapter=ADAPTER_NAME,
            run_id=self.run_id,
            seed=self.seed,
            timestamp=timestamp,
            venue=VENUE_NAME,
            intent=intent,
        )
        order_id: Optional[str] = None
        order: Optional[Order] = None
        if validation.accepted:
            order_id = self._next_id()
            updated_intent = replace(intent, client_order_id=validation.client_order_id)
            order = Order(order_id=order_id, intent=updated_intent, state=OrderState.SUBMITTED)
            self._orders[order_id] = order
        self._append_log(action="place_order", order_id=order_id, validation=validation, timestamp=timestamp)
        if not validation.accepted:
            raise ValueError(validation.reason)
        assert order is not None
        return order

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        timestamp = self.time_provider.utc_now().isoformat()
        validation = validate_request(
            adapter=ADAPTER_NAME,
            run_id=self.run_id,
            seed=self.seed,
            timestamp=timestamp,
            venue=VENUE_NAME,
            intent=intent,
        )
        updated: Optional[Order] = None
        if validation.accepted:
            updated_intent = replace(intent, client_order_id=validation.client_order_id)
            updated = replace(self._orders[order_id], intent=updated_intent, state=OrderState.SUBMITTED)
            self._orders[order_id] = updated
        self._append_log(action="replace_order", order_id=order_id, validation=validation, timestamp=timestamp)
        if not validation.accepted:
            raise ValueError(validation.reason)
        assert updated is not None
        return updated

    def cancel_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        existing = self._orders[order_id]
        timestamp = self.time_provider.utc_now().isoformat()
        validation = validate_request(
            adapter=ADAPTER_NAME,
            run_id=self.run_id,
            seed=self.seed,
            timestamp=timestamp,
            venue=VENUE_NAME,
            intent=existing.intent,
        )
        canceled = replace(existing, state=OrderState.CANCELED)
        self._orders[order_id] = canceled
        self._append_log(action="cancel_order", order_id=order_id, validation=validation, timestamp=timestamp)
        return canceled

    def poll_fills(self) -> List[Fill]:
        return []

    def get_positions(self) -> List[Position]:
        return []

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            ts=self.time_provider.utc_now().timestamp(),
        )

    def reconcile(self) -> None:
        return None

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        return None

    def _next_id(self) -> str:
        return f"ALPACA-DRY-{next(self._seq):06d}"

    def _append_log(self, *, action: str, order_id: Optional[str], validation: ValidationResult, timestamp: str) -> None:
        normalized = dict(validation.normalized_payload)
        entry = {
            "adapter": ADAPTER_NAME,
            "adapter_mode": ADAPTER_MODE,
            "action": action,
            "order_id": order_id,
            "run_id": self.run_id,
            "seed": self.seed,
            "timestamp": timestamp,
            "venue": VENUE_NAME,
            "venue_label": self.base_url,
            "symbol": normalized.get("symbol"),
            "side": normalized.get("side"),
            "order_type": normalized.get("order_type"),
            "time_in_force": normalized.get("time_in_force"),
            "qty": normalized.get("qty"),
            "price": normalized.get("price"),
            "client_order_id": normalized.get("client_order_id"),
            "intent_hash": normalized.get("intent_hash"),
            "request": normalized,
            "response": {
                "accepted": validation.accepted,
                "reason": validation.reason,
                "normalized_payload": normalized,
                "client_order_id": validation.client_order_id,
                "validation_hash": validation.validation_hash,
                "adapter": ADAPTER_NAME,
                "adapter_mode": ADAPTER_MODE,
                "symbol": normalized.get("symbol"),
                "side": normalized.get("side"),
                "qty": normalized.get("qty"),
                "price": normalized.get("price"),
            },
        }
        self._logs.append(entry)


