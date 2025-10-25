from __future__ import annotations

from collections import deque
from typing import Any, Dict

import pytest

from logos.adapters.ccxt_hardened import CCXTHardenedAdapter
from logos.adapters.common import OrderConflictError, RateLimiter, RetryConfig


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


class DummyCCXTClient:
    def __init__(self) -> None:
        self.create_calls = 0
        self.cancel_requests: deque[Dict[str, Any]] = deque()
        self.open_orders: list[Dict[str, Any]] = []
        self.fail_first = True

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.create_calls += 1
        if self.fail_first:
            self.fail_first = False
            raise ConnectionError("temporary network error")
        order = {
            "id": f"order-{self.create_calls}",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "amount": amount,
            "price": price,
            "clientOrderId": params["clientOrderId"],
            "status": "open",
        }
        self.open_orders = [order]
        return order

    def cancel_order(self, order_id: str, symbol: str | None) -> Dict[str, Any]:
        self.cancel_requests.append({"id": order_id, "symbol": symbol})
        self.open_orders = [
            order for order in self.open_orders if order.get("id") != order_id
        ]
        return {
            "id": order_id,
            "symbol": symbol,
            "status": "canceled",
        }

    def fetch_open_orders(self) -> list[Dict[str, Any]]:
        return list(self.open_orders)


def test_ccxt_adapter_retries_and_enforces_idempotency() -> None:
    clock = FakeClock()
    adapter = CCXTHardenedAdapter(
        client=DummyCCXTClient(),
        retry_config=RetryConfig(max_attempts=3, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=10, period=1.0, time_fn=clock.now),
        sleeper=lambda _: None,
    )

    order = adapter.submit_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=0.1,
        price=20000.0,
        client_id="cid-1",
    )
    assert order["clientOrderId"] == "cid-1"
    assert adapter.audit_log[-1]["action"] == "submit_order"

    cached = adapter.submit_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=0.1,
        price=20000.0,
        client_id="cid-1",
    )
    assert cached == order

    with pytest.raises(OrderConflictError):
        adapter.submit_order(
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            amount=0.1,
            price=21000.0,
            client_id="cid-1",
        )


def test_ccxt_adapter_cancel_and_reconcile_tracks_state() -> None:
    clock = FakeClock()
    client = DummyCCXTClient()
    adapter = CCXTHardenedAdapter(
        client=client,
        retry_config=RetryConfig(max_attempts=2, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=10, period=1.0, time_fn=clock.now),
        sleeper=lambda _: None,
    )

    adapter.submit_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=0.1,
        price=20000.0,
        client_id="cid-keep",
    )
    client.open_orders = []

    report = adapter.reconcile()
    assert report["missing_remote"] == ["cid-keep"]

    client.fail_first = False
    client.open_orders = [
        {
            "id": "order-keep",
            "clientOrderId": "cid-keep",
        }
    ]
    report = adapter.reconcile()
    assert report["missing_remote"] == []
    assert report["untracked_remote"] == []

    client.open_orders.append({"id": "order-extra", "clientOrderId": "cid-extra"})
    report = adapter.reconcile()
    assert report["untracked_remote"] == ["cid-extra"]
