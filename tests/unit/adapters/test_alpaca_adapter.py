from __future__ import annotations

from typing import Any, Dict, List

import pytest

from logos.adapters.alpaca import AlpacaAdapter
from logos.adapters.common import FatalAdapterError, RateLimiter, RetryConfig


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


class DummyAlpacaClient:
    def __init__(self) -> None:
        self.submit_calls: List[Dict[str, Any]] = []
        self.cancelled: List[str] = []
        self.open_orders: List[Dict[str, Any]] = []
        self.failures = 1

    def submit_order(self, **kwargs: Any) -> Dict[str, Any]:
        self.submit_calls.append(kwargs)
        if self.failures:
            self.failures -= 1
            raise TimeoutError("transient error")
        order = {
            "id": f"alpaca-{len(self.submit_calls)}",
            "client_order_id": kwargs["client_order_id"],
            "status": "accepted",
        }
        self.open_orders = [order]
        return order

    def cancel_order_by_client_order_id(self, client_id: str) -> None:
        self.cancelled.append(client_id)
        self.open_orders = [
            order for order in self.open_orders if order.get("client_order_id") != client_id
        ]

    def list_orders(self, status: str) -> List[Dict[str, Any]]:
        if status != "open":
            return []
        return list(self.open_orders)


def test_alpaca_adapter_retries_and_tracks_orders() -> None:
    clock = FakeClock()
    client = DummyAlpacaClient()
    adapter = AlpacaAdapter(
        client=client,
        retry_config=RetryConfig(max_attempts=3, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=50, period=60.0, time_fn=clock.now),
        sleeper=lambda _: None,
    )

    order = adapter.submit_order(
        symbol="AAPL",
        qty=10,
        side="buy",
        order_type="limit",
        limit_price=189.5,
        client_id="alpaca-123",
    )
    assert order["client_order_id"] == "alpaca-123"
    assert client.submit_calls[-1]["client_order_id"] == "alpaca-123"

    adapter.cancel_order("alpaca-123")
    assert client.cancelled == ["alpaca-123"]

    client.open_orders = []
    report = adapter.reconcile()
    assert report["missing_remote"] == ["alpaca-123"]

    client.open_orders = [
        {"client_order_id": "alpaca-123"},
        {"client_order_id": "alpaca-extra"},
    ]
    report = adapter.reconcile()
    assert report["missing_remote"] == []
    assert report["untracked_remote"] == ["alpaca-extra"]


def test_alpaca_cancel_unknown_client_raises() -> None:
    adapter = AlpacaAdapter(
        client=DummyAlpacaClient(),
        retry_config=RetryConfig(max_attempts=1, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=50, period=60.0),
        sleeper=lambda _: None,
    )

    with pytest.raises(FatalAdapterError):
        adapter.cancel_order("missing")
