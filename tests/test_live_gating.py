from __future__ import annotations

from argparse import Namespace

import pytest

from logos.config import Settings
from logos.live import main as live_main


def _base_settings(mode: str = "live") -> Settings:
    return Settings(start="2024-01-01", end="2024-02-01", symbol="MSFT", mode=mode)


def _limits(**overrides: float) -> dict[str, float]:
    base = {
        "max_notional": 10_000.0,
        "max_position": 1_000.0,
        "max_drawdown_bps": 500.0,
        "portfolio_drawdown_cap": 0.2,
        "daily_portfolio_loss_cap": 0.1,
    }
    base.update(overrides)
    return base


def test_live_requires_acknowledgement_phrase() -> None:
    args = Namespace(live=True, ack_phrase=None, send_orders=False)
    with pytest.raises(SystemExit) as exc:
        live_main._evaluate_live_request(args, _base_settings(), _limits())
    assert "i-understand" in str(exc.value)
    assert "place-live-orders" in str(exc.value)


def test_live_requires_environment_flag() -> None:
    args = Namespace(live=True, ack_phrase="place-live-orders", send_orders=False)
    with pytest.raises(SystemExit) as exc:
        live_main._evaluate_live_request(args, _base_settings(mode="paper"), _limits())
    assert "MODE=live" in str(exc.value)


def test_live_requires_risk_limits() -> None:
    args = Namespace(live=True, ack_phrase="place-live-orders", send_orders=False)
    with pytest.raises(SystemExit) as exc:
        live_main._evaluate_live_request(
            args, _base_settings(), _limits(max_notional=0.0)
        )
    message = str(exc.value)
    assert "risk.max_notional" in message
    assert "Safety Summary" in message


def test_live_gating_returns_live_without_send_orders() -> None:
    args = Namespace(
        live=True,
        ack_phrase="place-live-orders",
        send_orders=False,
    )
    mode, send = live_main._evaluate_live_request(args, _base_settings(), _limits())
    assert mode == "live"
    assert send is False


def test_live_gating_returns_live_with_send_orders() -> None:
    args = Namespace(
        live=True,
        ack_phrase="place-live-orders",
        send_orders=True,
    )
    mode, send = live_main._evaluate_live_request(args, _base_settings(), _limits())
    assert mode == "live"
    assert send is True


def test_live_absent_flag_defaults_to_paper() -> None:
    args = Namespace(live=False, ack_phrase=None, send_orders=False)
    mode, send = live_main._evaluate_live_request(args, _base_settings(), _limits())
    assert mode == "paper"
    assert send is False
