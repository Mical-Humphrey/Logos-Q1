"""Deterministic Alpaca dry-run broker adapter."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import count
from typing import Dict, List, Tuple

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


def _decimal_to_str(value: float | None) -> str | None:
    if value is None:
        return None
    dec = Decimal(str(value)).quantize(Decimal("0.00000001"))
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _intent_fingerprint(intent: OrderIntent) -> str:
    payload = {
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": _decimal_to_str(intent.quantity),
        "order_type": intent.order_type,
        "limit_price": _decimal_to_str(intent.limit_price),
        "time_in_force": intent.time_in_force,
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def _validation_pass() -> Dict[str, object]:
    return {"status": "accepted", "reason": None}


def _validation_fail(reason: str) -> Dict[str, object]:
    return {"status": "rejected", "reason": reason}


@dataclass
class AlpacaBrokerAdapter(BrokerAdapter):
    """Dry-run Alpaca adapter with deterministic structured logging."""

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

    # ------------------------------------------------------------------
    # BrokerAdapter contract
    # ------------------------------------------------------------------
    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        meta = SymbolMeta(symbol=symbol)
        self._append_log(
            action="get_symbol_meta",
            order_id="N/A",
            intent=None,
            extra_request={"symbol": symbol},
            response=_validation_pass(),
        )
        return meta

    def place_order(self, intent: OrderIntent) -> Order:
        if not self.dry_run:
            raise NotImplementedError("Live Alpaca integration not implemented")
        order_id = self._next_id()
        valid, reason = self._validate_intent(intent)
        response = _validation_pass() if valid else _validation_fail(reason)
        self._append_log(
            action="place_order",
            order_id=order_id,
            intent=intent,
            response=response,
        )
        if not valid:
            raise ValueError(reason)
        order = Order(order_id=order_id, intent=intent, state=OrderState.SUBMITTED)
        self._orders[order_id] = order
        return order

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        valid, reason = self._validate_intent(intent)
        response = _validation_pass() if valid else _validation_fail(reason)
        self._append_log(
            action="replace_order",
            order_id=order_id,
            intent=intent,
            response=response,
        )
        if not valid:
            raise ValueError(reason)
        existing = self._orders[order_id]
        updated = dataclasses.replace(existing, intent=intent, state=OrderState.SUBMITTED)
        self._orders[order_id] = updated
        return updated

    def cancel_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Unknown order_id {order_id}")
        order = self._orders[order_id]
        response = _validation_pass()
        self._append_log(
            action="cancel_order",
            order_id=order_id,
            intent=order.intent,
            response=response,
        )
        updated = dataclasses.replace(order, state=OrderState.CANCELED)
        self._orders[order_id] = updated
        return updated

    def poll_fills(self) -> list[Fill]:
        self._append_log(
            action="poll_fills",
            order_id="N/A",
            intent=None,
            extra_request={},
            response=_validation_pass(),
        )
        return []

    def get_positions(self) -> list[Position]:
        self._append_log(
            action="get_positions",
            order_id="N/A",
            intent=None,
            extra_request={},
            response=_validation_pass(),
        )
        return []

    def get_account(self) -> AccountSnapshot:
        snapshot = AccountSnapshot(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            ts=self.time_provider.utc_now().timestamp(),
        )
        self._append_log(
            action="get_account",
            order_id="N/A",
            intent=None,
            extra_request={"equity": snapshot.equity, "cash": snapshot.cash},
            response=_validation_pass(),
        )
        return snapshot

    def reconcile(self) -> None:
        self._append_log(
            action="reconcile",
            order_id="N/A",
            intent=None,
            extra_request={},
            response=_validation_pass(),
        )

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        self._append_log(
            action="market_data",
            order_id="N/A",
            intent=None,
            extra_request={
                "symbol": symbol,
                "price": _decimal_to_str(price),
                "ts": ts,
            },
            response=_validation_pass(),
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    @property
    def logs(self) -> List[dict]:
        return list(self._logs)

    def reset_logs(self) -> None:
        self._logs.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _next_id(self) -> str:
        return f"ALPACA-DRY-{next(self._seq):06d}"

    def _validate_intent(self, intent: OrderIntent) -> Tuple[bool, str]:
        if intent.quantity <= 0:
            return False, "non_positive_quantity"
        if intent.side not in {"buy", "sell"}:
            return False, "unsupported_side"
        if intent.order_type not in {"market", "limit"}:
            return False, "unsupported_order_type"
        if intent.order_type == "limit" and intent.limit_price is None:
            return False, "limit_price_required"
        return True, ""

    def _append_log(
        self,
        *,
        action: str,
        order_id: str,
        intent: OrderIntent | None,
        response: Dict[str, object],
        extra_request: Dict[str, object] | None = None,
    ) -> None:
        now = self.time_provider.utc_now()
        request_payload = {
            "action": action,
            "order_type": intent.order_type if intent else None,
            "time_in_force": intent.time_in_force if intent else None,
            "symbol": intent.symbol if intent else extra_request.get("symbol") if extra_request else None,
            "side": intent.side if intent else extra_request.get("side") if extra_request else None,
            "quantity": _decimal_to_str(intent.quantity) if intent else extra_request.get("quantity") if extra_request else None,
            "price": _decimal_to_str(intent.limit_price) if intent and intent.limit_price is not None else extra_request.get("price") if extra_request else None,
        }
        if extra_request:
            request_payload.update(extra_request)
        entry = {
            "adapter": "alpaca",
            "action": action,
            "venue": self.base_url,
            "run_id": self.run_id,
            "seed": self.seed,
            "clock": now.isoformat(),
            "order_id": order_id,
            "symbol": request_payload.get("symbol"),
            "side": request_payload.get("side"),
            "qty": request_payload.get("quantity"),
            "price": request_payload.get("price"),
            "intent_hash": _intent_fingerprint(intent) if intent is not None else None,
            "request": request_payload,
            "response": response,
        }
        self._logs.append(entry)


