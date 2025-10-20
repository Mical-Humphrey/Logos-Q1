"""Shared validation and serialization helpers for dry-run broker adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict

from .broker_base import OrderIntent

SUPPORTED_SIDES = {"buy", "sell"}
SUPPORTED_ORDER_TYPES = {"market", "limit"}
SUPPORTED_TIME_IN_FORCE = {"day", "gtc", "ioc", "fok"}


def _decimal_to_str(value: float | None) -> str | None:
    if value is None:
        return None
    dec = Decimal(str(value)).quantize(Decimal("0.00000001"))
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def intent_fingerprint(intent: OrderIntent) -> str:
    payload = {
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": _decimal_to_str(intent.quantity),
        "order_type": intent.order_type,
        "time_in_force": intent.time_in_force,
        "limit_price": _decimal_to_str(intent.limit_price),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def derive_client_order_id(seed: int, intent_hash: str, prefix: str = "DRY") -> str:
    """Derive a deterministic client order id from the seed + intent hash."""

    suffix = intent_hash[:24]
    client_id = f"{prefix}-{seed % 1_000_000:06d}-{suffix}"
    return client_id[:48]


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str
    normalized_payload: Dict[str, object]
    client_order_id: str
    validation_hash: str


def validate_request(
    *,
    adapter: str,
    run_id: str,
    seed: int,
    timestamp: str,
    venue: str,
    intent: OrderIntent,
) -> ValidationResult:
    side = intent.side
    order_type = intent.order_type
    time_in_force = intent.time_in_force or "gtc"
    qty = intent.quantity
    price = intent.limit_price if order_type == "limit" else None

    if not run_id:
        return _reject(
            "missing_run_id", adapter, run_id, seed, timestamp, venue, intent
        )
    if side not in SUPPORTED_SIDES:
        return _reject("invalid_side", adapter, run_id, seed, timestamp, venue, intent)
    if order_type not in SUPPORTED_ORDER_TYPES:
        return _reject(
            "invalid_order_type", adapter, run_id, seed, timestamp, venue, intent
        )
    if time_in_force not in SUPPORTED_TIME_IN_FORCE:
        return _reject(
            "invalid_time_in_force", adapter, run_id, seed, timestamp, venue, intent
        )
    if qty is None or qty <= 0:
        return _reject(
            "qty_not_positive", adapter, run_id, seed, timestamp, venue, intent
        )
    if order_type == "limit":
        if price is None:
            return _reject(
                "limit_price_required", adapter, run_id, seed, timestamp, venue, intent
            )
        if price <= 0:
            return _reject(
                "limit_price_not_positive",
                adapter,
                run_id,
                seed,
                timestamp,
                venue,
                intent,
            )

    intent_hash = intent_fingerprint(intent)
    client_order_id = derive_client_order_id(seed, intent_hash)

    normalized = {
        "adapter": adapter,
        "run_id": run_id,
        "seed": seed,
        "timestamp": timestamp,
        "venue": venue,
        "symbol": intent.symbol,
        "side": side,
        "order_type": order_type,
        "time_in_force": time_in_force,
        "qty": _decimal_to_str(qty),
        "price": _decimal_to_str(price) if price is not None else None,
        "client_order_id": client_order_id,
        "intent_hash": intent_hash,
    }

    validation_hash = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return ValidationResult(
        accepted=True,
        reason="",
        normalized_payload=normalized,
        client_order_id=client_order_id,
        validation_hash=validation_hash,
    )


def _reject(
    reason: str,
    adapter: str,
    run_id: str,
    seed: int,
    timestamp: str,
    venue: str,
    intent: OrderIntent,
) -> ValidationResult:
    intent_hash = intent_fingerprint(intent)
    client_order_id = derive_client_order_id(seed, intent_hash)
    normalized = {
        "adapter": adapter,
        "run_id": run_id,
        "seed": seed,
        "timestamp": timestamp,
        "venue": venue,
        "symbol": intent.symbol,
        "side": intent.side,
        "order_type": intent.order_type,
        "time_in_force": intent.time_in_force or "gtc",
        "qty": _decimal_to_str(intent.quantity),
        "price": (
            _decimal_to_str(intent.limit_price)
            if intent.limit_price is not None
            else None
        ),
        "client_order_id": client_order_id,
        "intent_hash": intent_hash,
    }
    validation_hash = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ValidationResult(
        accepted=False,
        reason=reason,
        normalized_payload=normalized,
        client_order_id=client_order_id,
        validation_hash=validation_hash,
    )
