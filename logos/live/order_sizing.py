"""Helpers that translate strategy targets into broker orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .broker_base import OrderIntent, SymbolMeta, quantize_order, meets_minimums


@dataclass
class TargetPosition:
    """Desired position after executing generated orders."""

    symbol: str
    quantity: float


@dataclass
class SizingConfig:
    """Risk-aware sizing knobs."""

    max_notional: float = 0.0
    max_position: float = 0.0


def _clamp_to_notional(qty: float, price: float, max_notional: float) -> float:
    if max_notional <= 0:
        return qty
    notional = abs(qty * price)
    if notional <= max_notional:
        return qty
    scale = max_notional / notional
    return qty * scale


def generate_order_intents(
    current_qty: float,
    target: TargetPosition,
    price: float,
    meta: SymbolMeta,
    sizing: SizingConfig,
) -> List[OrderIntent]:
    """Create one or more intents needed to reach the target quantity."""

    delta = target.quantity - current_qty
    if abs(delta) < 1e-9:
        return []
    clamped = _clamp_to_notional(delta, price, sizing.max_notional)
    if sizing.max_position > 0:
        desired = current_qty + clamped
        if abs(desired) > sizing.max_position:
            clamped = sizing.max_position * (1 if desired > 0 else -1) - current_qty
    qty, eff_price = quantize_order(clamped, price, meta)
    if qty == 0:
        return []
    if not meets_minimums(qty, eff_price, meta):
        return []
    side = "buy" if qty > 0 else "sell"
    intent = OrderIntent(symbol=target.symbol, side=side, quantity=abs(qty))
    return [intent]


def flatten_intents(intents: Iterable[OrderIntent]) -> List[OrderIntent]:
    """Normalize iterable inputs to a list (small ergonomic helper)."""

    return list(intents)
