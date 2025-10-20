"""Interactive Brokers adapter placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from .broker_base import (
    AccountSnapshot,
    BrokerAdapter,
    Fill,
    Order,
    OrderIntent,
    Position,
    SymbolMeta,
)
from .time import TimeProvider, SystemTimeProvider


@dataclass
class IBBrokerAdapter(BrokerAdapter):
    """Placeholder for a future IBKR integration."""

    host: str
    port: int
    client_id: int = 999
    time_provider: TimeProvider = SystemTimeProvider()

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        return SymbolMeta(symbol=symbol)

    def place_order(self, intent: OrderIntent) -> Order:
        raise NotImplementedError("IBKR adapter not yet implemented")

    def replace_order(self, order_id: str, intent: OrderIntent) -> Order:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> Order:
        raise NotImplementedError

    def poll_fills(self) -> list[Fill]:
        return []

    def get_positions(self) -> list[Position]:
        return []

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            ts=self.time_provider.utc_now().timestamp(),
        )

    def reconcile(self) -> None:
        return

    def on_market_data(self, symbol: str, price: float, ts: float) -> None:
        return
