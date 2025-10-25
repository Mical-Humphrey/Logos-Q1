from __future__ import annotations

from typing import Any, Dict, List

import pytest

from logos.adapters.common import FatalAdapterError, RateLimiter, RetryConfig
from logos.adapters.oanda import OandaAdapter


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


class DummyOandaClient:
    def __init__(self) -> None:
        self.created: List[Dict[str, Any]] = []
        self.pending: List[Dict[str, Any]] = []
        self.cancelled: List[str] = []
        self.failures = 1

    def create_order(self, account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.created.append({"account_id": account_id, **payload})
        if self.failures:
            self.failures -= 1
            raise TimeoutError("network hiccup")
        cid = payload["order"]["clientExtensions"]["id"]
        order = {
            "id": f"order-{len(self.pending) + 1}",
            "clientExtensions": {"id": cid},
        }
        self.pending = [order]
        return order

    def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        self.cancelled.append(order_id)
        self.pending = [order for order in self.pending if order.get("id") != order_id]
        return {"id": order_id, "state": "CANCELLED"}

    def list_pending_orders(self, account_id: str) -> List[Dict[str, Any]]:
        return list(self.pending)


def test_oanda_adapter_generates_signed_units_and_retries() -> None:
    clock = FakeClock()
    client = DummyOandaClient()
    adapter = OandaAdapter(
        client=client,
        account_id="demo-account",
        retry_config=RetryConfig(max_attempts=3, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=120, period=60.0, time_fn=clock.now),
        sleeper=lambda _: None,
    )

    order = adapter.submit_order(
        instrument="EUR_USD",
        units=1000,
        side="sell",
        order_type="LIMIT",
        price=1.1,
        client_id="oanda-1",
    )
    assert order["clientExtensions"]["id"] == "oanda-1"
    payload = client.created[-1]["order"]
    assert payload["units"] == -1000

    adapter.cancel_order("oanda-1")
    assert client.cancelled == [order["id"]]

    client.pending = []
    report = adapter.reconcile()
    assert report["missing_remote"] == ["oanda-1"]

    client.pending = [
        {"clientExtensions": {"id": "oanda-1"}},
        {"clientExtensions": {"id": "oanda-extra"}},
    ]
    report = adapter.reconcile()
    assert report["missing_remote"] == []
    assert report["untracked_remote"] == ["oanda-extra"]


def test_oanda_adapter_cancel_unknown_id_raises() -> None:
    adapter = OandaAdapter(
        client=DummyOandaClient(),
        account_id="demo-account",
        retry_config=RetryConfig(max_attempts=1, base_delay=0.0, backoff=1.0, jitter=0.0, max_delay=0.0),
        rate_limiter=RateLimiter(max_calls=120, period=60.0),
        sleeper=lambda _: None,
    )

    with pytest.raises(FatalAdapterError):
        adapter.cancel_order("missing")
