"""Minimal CCXT adapter scaffolding.

The real implementation will translate between the BrokerAdapter
contract and CCXT's asynchronous REST client.  For now we provide a
lightweight shell that raises ``NotImplementedError`` for order
operations but exposes configuration wiring and TODO notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .broker_base import AccountSnapshot, BrokerAdapter, Order, OrderIntent, Fill, Position, SymbolMeta
from .time import TimeProvider, SystemTimeProvider


@dataclass
class CCXTBrokerAdapter(BrokerAdapter):
    """CCXT-backed broker adapter (stub)."""

    exchange: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    time_provider: TimeProvider = SystemTimeProvider()

    def __post_init__(self) -> None:
        # TODO: instantiate ccxt client here (lazy init for tests).
        self._client = None

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        # TODO: fetch symbol info from exchange metadata.
        return SymbolMeta(symbol=symbol)

    def place_order(self, intent: OrderIntent) -> Order:
        raise NotImplementedError("CCXT order placement not implemented yet")

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> Order:
        raise NotImplementedError

    def poll_fills(self) -> list[Fill]:
        return []

    def get_positions(self) -> list[Position]:
        return []

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(equity=0.0, cash=0.0, buying_power=0.0, ts=self.time_provider.utc_now().timestamp())

    def reconcile(self) -> None:
        # TODO: sync with exchange balances/orders.
        return

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        # No-op for now; future versions may track mark-to-market.
        return
