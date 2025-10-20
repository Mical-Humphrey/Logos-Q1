"""Deterministic paper broker scaffold.

Sprint A will implement FIFO inventory, deterministic fills, event logging, and
account snapshots. This stub exists so failing-first tests can describe the
expected behaviour ahead of implementation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List

from logos.live.types import Account, Event, EventType, Order, OrderIntent


class PaperBroker:
    """Placeholder deterministic paper broker."""

    def __init__(self, metadata_registry, starting_account: Account) -> None:
        self.metadata_registry = metadata_registry
        self._starting_account = starting_account

    def submit_order(self, intent: OrderIntent) -> Order:
        """Submit an order intent to the broker."""

        raise NotImplementedError("Paper broker submit flow not implemented yet")

    def record_fill(self, order_id: str, *, price: Decimal, quantity: Decimal) -> None:
        """Record a deterministic fill for an existing order."""

        raise NotImplementedError("Paper broker fill handling not implemented yet")

    def cancel_order(self, order_id: str) -> None:
        """Cancel an existing order."""

        raise NotImplementedError("Paper broker cancel not implemented yet")

    def account_snapshot(self) -> Account:
        """Return the latest account snapshot."""

        raise NotImplementedError("Paper broker account snapshot not implemented yet")

    def events_for_order(self, order_id: str) -> List[Event]:
        """Return the event trail for an order."""

        raise NotImplementedError("Paper broker event log not implemented yet")
