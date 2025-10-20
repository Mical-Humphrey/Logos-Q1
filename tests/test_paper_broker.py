import datetime as dt

import pytest

from logos.live.broker_base import OrderIntent, OrderState, Position, SymbolMeta
from logos.live.broker_paper import PaperBrokerAdapter


@pytest.fixture()
def broker():
    broker = PaperBrokerAdapter(slippage_bps=1.0, fee_bps=0.0)
    broker.set_symbol_meta(SymbolMeta(symbol="MSFT", price_precision=2, quantity_precision=2))
    return broker


def _latest_fill(broker: PaperBrokerAdapter):
    fills = broker.poll_fills()
    assert len(fills) == 1
    return fills[0]


def test_market_order_fill_updates_cash_and_positions(broker: PaperBrokerAdapter):
    intent = OrderIntent(symbol="MSFT", side="buy", quantity=10.0, order_type="market")
    order = broker.place_order(intent)
    assert order.state == OrderState.SUBMITTED

    ts = dt.datetime(2025, 1, 1, 9, 30, tzinfo=dt.timezone.utc).timestamp()
    broker.on_market_data("MSFT", price=100.0, ts=ts)

    fill = _latest_fill(broker)
    assert fill.price == pytest.approx(100.01, rel=1e-5)
    assert fill.quantity == pytest.approx(10.0)

    positions = broker.get_positions()
    assert len(positions) == 1
    pos = positions[0]
    assert isinstance(pos, Position)
    assert pos.symbol == "MSFT"
    assert pos.quantity == pytest.approx(10.0)
    assert pos.avg_price == pytest.approx(fill.price)

    account = broker.get_account()
    expected_cash = broker.starting_cash - fill.price * fill.quantity
    assert account.cash == pytest.approx(expected_cash)
    expected_equity = expected_cash + pos.quantity * 100.0
    assert account.equity == pytest.approx(expected_equity)


def test_limit_order_waits_for_price_and_uses_limit_cap(broker: PaperBrokerAdapter):
    intent = OrderIntent(symbol="MSFT", side="buy", quantity=5.0, order_type="limit", limit_price=100.0)
    broker.place_order(intent)

    ts1 = dt.datetime(2025, 1, 1, 9, 31, tzinfo=dt.timezone.utc).timestamp()
    broker.on_market_data("MSFT", price=101.0, ts=ts1)
    assert broker.poll_fills() == []

    ts2 = dt.datetime(2025, 1, 1, 9, 32, tzinfo=dt.timezone.utc).timestamp()
    broker.on_market_data("MSFT", price=99.0, ts=ts2)
    fill = _latest_fill(broker)
    assert fill.price == pytest.approx(99.01, rel=1e-5)


def test_bootstrap_positions_sets_cash_and_marks(broker: PaperBrokerAdapter):
    broker.bootstrap_positions({
        "MSFT": {"qty": 8.0, "avg_price": 50.0, "realized": 0.0},
        "TSLA": {"qty": -2.0, "avg_price": 200.0, "realized": 10.0},
    })
    positions = broker.get_positions()
    assert {p.symbol for p in positions} == {"MSFT", "TSLA"}
    msft = next(p for p in positions if p.symbol == "MSFT")
    tsla = next(p for p in positions if p.symbol == "TSLA")
    assert msft.quantity == pytest.approx(8.0)
    assert msft.avg_price == pytest.approx(50.0)
    assert tsla.quantity == pytest.approx(-2.0)
    assert tsla.avg_price == pytest.approx(200.0)

    account = broker.get_account()
    expected_cash = broker.starting_cash - (8.0 * 50.0) - (-2.0 * 200.0)
    assert account.cash == pytest.approx(expected_cash)
