from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from core.io.atomic_write import atomic_write_text


@dataclass(frozen=True)
class OrderRequest:
    """Incoming order request emitted by a strategy."""

    strategy_id: str
    symbol: str
    quantity: float
    price: float
    client_order_id: str
    idempotency_key: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class OrderDecision:
    """Decision returned by the router when processing an order request."""

    accepted: bool
    order_id: Optional[str]
    reason: str = ""


@dataclass(frozen=True)
class FillReport:
    """External fill/update information supplied by the broker layer."""

    order_id: str
    status: str
    filled_qty: float
    timestamp: datetime


@dataclass(frozen=True)
class ReconciliationResult:
    """Summary returned by :meth:`OrderRouter.reconcile`."""

    resolved: Tuple[str, ...]
    unknown_fills: Tuple[str, ...]
    remaining_inflight: int


@dataclass(frozen=True)
class RouterSnapshot:
    """Serializable representation of router state for restart persistence."""

    rate_limit_per_sec: int
    max_inflight: int
    next_sequence: int
    halted: bool
    rate_counters: Dict[str, Tuple[str, ...]]
    inflight: Dict[str, Dict[str, object]]
    idempotency: Dict[str, Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "rate_limit_per_sec": self.rate_limit_per_sec,
            "max_inflight": self.max_inflight,
            "next_sequence": self.next_sequence,
            "halted": self.halted,
            "rate_counters": {
                strategy: list(entries)
                for strategy, entries in self.rate_counters.items()
            },
            "inflight": self.inflight,
            "idempotency": self.idempotency,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "RouterSnapshot":
        return cls(
            rate_limit_per_sec=int(payload["rate_limit_per_sec"]),
            max_inflight=int(payload["max_inflight"]),
            next_sequence=int(payload["next_sequence"]),
            halted=bool(payload["halted"]),
            rate_counters={
                key: tuple(str(entry) for entry in value)  # type: ignore[list-item]
                for key, value in (payload.get("rate_counters", {}) or {}).items()
            },
            inflight={
                key: dict(value)
                for key, value in (payload.get("inflight", {}) or {}).items()
            },
            idempotency={
                key: dict(value)
                for key, value in (payload.get("idempotency", {}) or {}).items()
            },
        )


class OrderRouter:
    """Centralise order submission with guardrails.

    Features:
    - Per-strategy rate limiting (sliding one-second window).
    - Idempotent `client_order_id` handling.
    - In-flight tracking with reconciliation and fail-closed semantics.
    """

    def __init__(
        self,
        *,
        rate_limit_per_sec: int = 5,
        max_inflight: int = 256,
    ) -> None:
        if rate_limit_per_sec <= 0:  # pragma: no cover - guard
            raise ValueError("rate_limit_per_sec must be positive")
        if max_inflight <= 0:  # pragma: no cover - guard
            raise ValueError("max_inflight must be positive")
        self._rate_limit = rate_limit_per_sec
        self._max_inflight = max_inflight
        self._rate_counters: Dict[str, Deque[datetime]] = defaultdict(deque)
        self._inflight: Dict[str, OrderRequest] = {}
        self._idempotency: Dict[str, OrderDecision] = {}
        self._next_seq = 1
        self._halted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(
        self, request: OrderRequest, *, now: Optional[datetime] = None
    ) -> OrderDecision:
        if self._halted:
            return OrderDecision(False, None, reason="router_halted")
        timestamp = now or request.timestamp or datetime.utcnow()
        key = (
            request.idempotency_key
            or f"{request.strategy_id}:{request.client_order_id}"
        )
        if key in self._idempotency:
            return self._idempotency[key]

        self._prune_rate_window(request.strategy_id, timestamp)
        window = self._rate_counters[request.strategy_id]
        if len(window) >= self._rate_limit:
            decision = OrderDecision(False, None, reason="rate_limited")
            self._idempotency[key] = decision
            return decision

        if len(self._inflight) >= self._max_inflight:
            decision = OrderDecision(False, None, reason="inflight_limit")
            self._idempotency[key] = decision
            return decision

        order_id = f"ROUTER-{self._next_seq:08d}"
        self._next_seq += 1
        decision = OrderDecision(True, order_id, reason="accepted")
        self._inflight[order_id] = request
        window.append(timestamp)
        self._idempotency[key] = decision
        return decision

    def reconcile(self, fills: Iterable[FillReport]) -> ReconciliationResult:
        resolved: List[str] = []
        unknown: List[str] = []
        for fill in fills:
            if fill.order_id not in self._inflight:
                unknown.append(fill.order_id)
                continue
            request = self._inflight.pop(fill.order_id)
            key = (
                request.idempotency_key
                or f"{request.strategy_id}:{request.client_order_id}"
            )
            decision = self._idempotency.get(key)
            if decision is not None:
                # Replace stored decision result with terminal status
                self._idempotency[key] = OrderDecision(
                    decision.accepted,
                    decision.order_id,
                    reason=fill.status.lower(),
                )
            resolved.append(fill.order_id)
        if unknown:
            self._halted = True
        return ReconciliationResult(
            resolved=tuple(resolved),
            unknown_fills=tuple(unknown),
            remaining_inflight=len(self._inflight),
        )

    def pending_orders(self) -> Dict[str, OrderRequest]:
        return dict(self._inflight)

    def halted(self) -> bool:
        return self._halted

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def snapshot(self) -> RouterSnapshot:
        return RouterSnapshot(
            rate_limit_per_sec=self._rate_limit,
            max_inflight=self._max_inflight,
            next_sequence=self._next_seq,
            halted=self._halted,
            rate_counters={
                strategy: tuple(ts.isoformat() for ts in window)
                for strategy, window in self._rate_counters.items()
            },
            inflight={
                order_id: self._serialize_request(request)
                for order_id, request in self._inflight.items()
            },
            idempotency={
                key: self._serialize_decision(decision)
                for key, decision in self._idempotency.items()
            },
        )

    def restore(self, snapshot: RouterSnapshot) -> None:
        if snapshot.rate_limit_per_sec != self._rate_limit:
            raise ValueError("snapshot rate limit does not match router configuration")
        if snapshot.max_inflight != self._max_inflight:
            raise ValueError(
                "snapshot max inflight does not match router configuration"
            )
        self._next_seq = snapshot.next_sequence
        self._halted = snapshot.halted
        self._rate_counters = defaultdict(
            deque,
            {
                strategy: deque(datetime.fromisoformat(ts) for ts in entries)
                for strategy, entries in snapshot.rate_counters.items()
            },
        )
        self._inflight = {
            order_id: self._deserialize_request(payload)
            for order_id, payload in snapshot.inflight.items()
        }
        self._idempotency = {
            key: self._deserialize_decision(payload)
            for key, payload in snapshot.idempotency.items()
        }

    def save(self, path: Path) -> Path:
        payload = self.snapshot().to_dict()
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "OrderRouter":
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = RouterSnapshot.from_dict(payload)
        router = cls(
            rate_limit_per_sec=snapshot.rate_limit_per_sec,
            max_inflight=snapshot.max_inflight,
        )
        router.restore(snapshot)
        return router

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prune_rate_window(self, strategy_id: str, now: datetime) -> None:
        window = self._rate_counters[strategy_id]
        cutoff = now - timedelta(seconds=1)
        while window and window[0] < cutoff:
            window.popleft()

    @staticmethod
    def _serialize_request(request: OrderRequest) -> Dict[str, object]:
        return {
            "strategy_id": request.strategy_id,
            "symbol": request.symbol,
            "quantity": request.quantity,
            "price": request.price,
            "client_order_id": request.client_order_id,
            "idempotency_key": request.idempotency_key,
            "timestamp": request.timestamp.isoformat() if request.timestamp else None,
        }

    @staticmethod
    def _deserialize_request(payload: Dict[str, object]) -> OrderRequest:
        timestamp_value = payload.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_value)
            if isinstance(timestamp_value, str) and timestamp_value
            else None
        )
        client_order_id = payload.get("client_order_id")
        idempotency_key = payload.get("idempotency_key")
        return OrderRequest(
            strategy_id=str(payload.get("strategy_id")),
            symbol=str(payload.get("symbol")),
            quantity=float(payload.get("quantity", 0.0)),
            price=float(payload.get("price", 0.0)),
            client_order_id=(
                str(client_order_id) if client_order_id is not None else None
            ),
            idempotency_key=(
                str(idempotency_key) if idempotency_key is not None else None
            ),
            timestamp=timestamp,
        )

    @staticmethod
    def _serialize_decision(decision: OrderDecision) -> Dict[str, object]:
        return {
            "accepted": decision.accepted,
            "order_id": decision.order_id,
            "reason": decision.reason,
        }

    @staticmethod
    def _deserialize_decision(payload: Dict[str, object]) -> OrderDecision:
        return OrderDecision(
            accepted=bool(payload.get("accepted")),
            order_id=(
                str(payload.get("order_id"))
                if payload.get("order_id") is not None
                else None
            ),
            reason=str(payload.get("reason", "")),
        )


__all__ = [
    "OrderRouter",
    "OrderRequest",
    "OrderDecision",
    "FillReport",
    "ReconciliationResult",
    "RouterSnapshot",
]
