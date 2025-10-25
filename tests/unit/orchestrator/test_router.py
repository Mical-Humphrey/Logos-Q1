from __future__ import annotations

import datetime as dt

import pytest

from logos.orchestrator.router import (
    FillReport,
    OrderDecision,
    OrderRequest,
    OrderRouter,
)


def _req(client_order_id: str, *, ts: dt.datetime | None = None) -> OrderRequest:
    return OrderRequest(
        strategy_id="alpha",
        symbol="MSFT",
        quantity=10.0,
        price=100.0,
        client_order_id=client_order_id,
        timestamp=ts,
    )


def test_router_rate_limiting_and_idempotency():
    router = OrderRouter(rate_limit_per_sec=2, max_inflight=10)
    now = dt.datetime(2025, 1, 1, 12, 0, 0)
    first = router.submit(_req("A1", ts=now), now=now)
    second_ts = now + dt.timedelta(milliseconds=10)
    second = router.submit(_req("A2", ts=second_ts), now=second_ts)
    third_ts = now + dt.timedelta(milliseconds=20)
    third = router.submit(_req("A3", ts=third_ts), now=third_ts)

    assert first.accepted
    assert second.accepted
    assert not third.accepted
    assert third.reason == "rate_limited"

    # Idempotent replay
    replay_ts = now + dt.timedelta(seconds=1)
    replay = router.submit(_req("A1", ts=replay_ts), now=replay_ts)
    assert replay.order_id == first.order_id
    assert replay.accepted == first.accepted


def test_router_reconciliation_and_fail_closed():
    router = OrderRouter(rate_limit_per_sec=5, max_inflight=5)
    now = dt.datetime.utcnow()
    decision = router.submit(_req("B1", ts=now), now=now)
    assert decision.accepted and decision.order_id is not None

    fill = FillReport(
        order_id=decision.order_id,
        status="filled",
        filled_qty=10.0,
        timestamp=now + dt.timedelta(seconds=1),
    )
    result = router.reconcile([fill])
    assert decision.order_id in result.resolved
    assert not result.unknown_fills
    assert result.remaining_inflight == 0

    # Unknown fill triggers halt (fail closed)
    router.reconcile(
        [
            FillReport(
                order_id="UNKNOWN",
                status="filled",
                filled_qty=1.0,
                timestamp=now,
            )
        ]
    )
    assert router.halted()
    later = now + dt.timedelta(seconds=2)
    rejection = router.submit(_req("B2", ts=later), now=later)
    assert not rejection.accepted
    assert rejection.reason == "router_halted"


def test_router_snapshot_roundtrip(tmp_path):
    router = OrderRouter(rate_limit_per_sec=2, max_inflight=4)
    now = dt.datetime(2025, 1, 1, 12, 0, 0)
    req1 = _req("C1", ts=now)
    dec1 = router.submit(req1, now=now)
    assert dec1.accepted
    req2 = _req("C2", ts=now + dt.timedelta(milliseconds=50))
    dec2 = router.submit(req2, now=now + dt.timedelta(milliseconds=50))
    assert dec2.accepted

    snapshot_path = tmp_path / "router.json"
    router.save(snapshot_path)
    assert snapshot_path.exists()

    restored = OrderRouter.load(snapshot_path)
    replay = restored.submit(req1, now=now + dt.timedelta(seconds=1))
    assert replay.order_id == dec1.order_id
    assert replay.accepted == dec1.accepted

    third_req = _req("C3", ts=now + dt.timedelta(milliseconds=75))
    third = restored.submit(third_req, now=now + dt.timedelta(milliseconds=75))
    assert not third.accepted
    assert third.reason == "rate_limited"
