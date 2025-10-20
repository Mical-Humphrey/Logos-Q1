"""Shared types for live trading components.

This module introduces the dataclasses and enumerations used by the translator,
paper broker, and runner subsystems. Implementations are deferred to Sprint A
and will initially be exercised via failing-first tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Tuple


class OrderSide(str, Enum):
    """Trade direction for generated orders."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Lifecycle states for live orders."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Events emitted by the paper broker during order execution."""

    SUBMITTED = "submitted"
    FILL = "fill"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Pricing:
    """Price container for limit and market orders."""

    limit: Optional[Decimal] = None
    stop: Optional[Decimal] = None


@dataclass
class SizingInstruction:
    """Sizing instructions provided by strategy signals."""

    mode: str
    value: Decimal

    @classmethod
    def fixed_notional(cls, value: Decimal) -> "SizingInstruction":
        """Create a fixed-notional sizing instruction."""

        return cls(mode="fixed_notional", value=value)

    @classmethod
    def percent_of_equity(cls, value: Decimal) -> "SizingInstruction":
        """Create a percent-of-equity sizing instruction."""

        return cls(mode="percent_of_equity", value=value)


@dataclass
class SymbolMetadata:
    """Market metadata required for quantisation and validation."""

    symbol: str
    venue_symbol: str
    price_precision: int
    quantity_precision: int
    lot_size: Decimal
    min_notional: Decimal
    max_notional: Decimal
    aliases: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class Position:
    """Tracked inventory for a given symbol."""

    symbol: str
    quantity: Decimal
    average_price: Decimal


@dataclass
class Account:
    """Snapshot of account balances and realised metrics."""

    equity: Decimal
    cash: Decimal
    positions: Dict[str, Position]
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")


@dataclass
class OrderIntent:
    """Intent produced by translator before broker submission."""

    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Pricing
    notional: Decimal
    metadata: SymbolMetadata
    sizing: SizingInstruction


@dataclass
class Order:
    """Order tracked by the paper broker."""

    id: str
    intent: OrderIntent
    status: OrderStatus
    filled_quantity: Decimal
    avg_fill_price: Optional[Decimal] = None


@dataclass
class Fill:
    """Fill event recorded by the paper broker."""

    order_id: str
    price: Decimal
    quantity: Decimal
    realized_pnl: Decimal


@dataclass
class Event:
    """Broker event emitted for audit logging."""

    order_id: str
    type: EventType
    payload: Dict[str, object] = field(default_factory=dict)